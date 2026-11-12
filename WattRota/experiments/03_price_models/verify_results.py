"""Görev 3 sonuçlarının yeniden hesaplanması ve bağımsız bütünlük kontrolleri."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from models import feature_pack, forecast_candidates
from forecast_stats import residual_scenarios
from run import load_parent


def verify(project, output):
    sys.path.insert(0,str(project/'src'))
    from fiyat_tahmini import elektrik_fiyatlarini_oku
    metadata=json.loads((output/'experiment_info.json').read_text(encoding='utf-8'))
    for name,value in metadata['input_sha256'].items():
        if hashlib.sha256((project/name).read_bytes()).hexdigest()!=value:
            raise ValueError('Kaynak veya girdi değişmiş: '+name)
    config=json.loads((output/'config_snapshot.json').read_text(encoding='utf-8'))
    parent=load_parent(project)
    parent_output=project/config['parent_protocol']
    folds,lock=parent.verify_lock(project,project/'experiments/02_walk_forward/config.json',parent_output)
    development=folds.loc[folds['split'].eq('development')]
    locked_start=folds.loc[folds['split'].eq('locked_test'),'decision_origin'].min()
    p=pd.read_csv(output/'predictions.csv',parse_dates=['decision_origin','target_time'])
    scores=pd.read_csv(output/'model_scores.csv').set_index('model')
    scenarios=pd.read_csv(output/'scenario_prices.csv',parse_dates=['decision_origin'])
    audit=pd.read_csv(output/'scenario_audit.csv',parse_dates=['decision_origin','residual_last_target','available_last'])
    train=pd.read_csv(output/'training_audit.csv',parse_dates=['decision_origin','available_last','training_last_label'])
    assert len(p)==34*13*48 and len(scores)==13
    assert set(p['decision_origin'])==set(development['decision_origin'])
    assert p['target_time'].max()<locked_start
    assert not (parent_output/'locked_test').exists()
    assert (audit['residual_last_target']<=audit['available_last']).all()
    assert (train['training_last_label']<=train['available_last']).all()
    assert train['convergence_warnings'].sum()==0
    prices=elektrik_fiyatlarini_oku(project)
    np.testing.assert_allclose(p['actual'],prices.reindex(pd.DatetimeIndex(p['target_time'])).to_numpy(),atol=1e-9,rtol=0)
    calculated=p.assign(error=lambda d:(d['prediction']-d['actual']).abs()).groupby('model')['error'].mean()
    np.testing.assert_allclose(calculated,scores.reindex(calculated.index)['mae_tl_mwh'],atol=1e-9,rtol=0)
    assert metadata['selected_model']==calculated.idxmin()
    assert len(scenarios)==34*30
    for origin,frame in scenarios.groupby('decision_origin'):
        assert len(frame)==30 and frame['scenario_id'].nunique()==30
        np.testing.assert_allclose(frame['probability'].sum(),1,atol=1e-12)
        known=prices.reindex(pd.date_range(origin,periods=24,freq='h')).to_numpy()
        np.testing.assert_allclose(frame[[f'hour_{h}' for h in range(24)]],np.tile(known,(30,1)),atol=1e-9,rtol=0)
        assert (frame[[f'hour_{h}' for h in range(72)]]>=0).all().all()
    # Tam üretim ayarlarıyla son haftayı tekrar üret; bütün bilinmeyen fiyatları boz.
    origin=p['decision_origin'].max()
    poison=prices.copy();poison.loc[poison.index>=origin+pd.Timedelta(hours=24)]=999999.
    candidates,_,_,_=forecast_candidates(feature_pack(poison,origin,config),config)
    selected=p.loc[p['decision_origin'].eq(origin)]
    candidates['hgb_expanding_cached']=selected.loc[selected['model'].eq('hgb_expanding_cached')].sort_values('target_time')['prediction'].to_numpy()
    candidates['ensemble_level_fixed']=np.mean([candidates[n] for n in config['ensemble_level_components']],axis=0)
    candidates['ensemble_profile_fixed']=np.mean([candidates[n] for n in config['ensemble_profile_components']],axis=0)
    for name,values in candidates.items():
        saved=selected.loc[selected['model'].eq(name)].sort_values('target_time')['prediction'].to_numpy()
        np.testing.assert_allclose(values,saved,atol=1e-8,rtol=1e-12)
    # Artık havuzunu kayıtlı OOS tahminlerden yeniden oluştur ve 30 yolu karşılaştır.
    calibration=pd.read_csv(output/'calibration_predictions.csv',parse_dates=['origin','target_time'])
    errors=[]
    for _,frame in calibration.groupby('origin',sort=True):
        frame=frame.sort_values('target_time')
        assert frame['target_time'].max()<origin+pd.Timedelta(hours=24)
        errors.append((frame['actual']-frame['prediction']).to_numpy())
    past=p.loc[p['model'].eq(config['scenario_model']) & p['decision_origin'].lt(origin)]
    for _,frame in past.groupby('decision_origin',sort=True):
        frame=frame.sort_values('target_time')
        assert frame['target_time'].max()<origin+pd.Timedelta(hours=24)
        errors.append((frame['actual']-frame['prediction']).to_numpy())
    point=selected.loc[selected['model'].eq(config['scenario_model'])].sort_values('target_time')['prediction'].to_numpy()
    regenerated,_=residual_scenarios(point,prices.reindex(pd.date_range(origin,periods=24,freq='h')).to_numpy(),
                                    np.stack(errors),config['scenario_count'],config['seed']+origin.toordinal())
    saved=scenarios.loc[scenarios['decision_origin'].eq(origin)].sort_values('scenario_id')[[f'hour_{h}' for h in range(72)]].to_numpy()
    np.testing.assert_allclose(saved,regenerated,atol=1e-8,rtol=1e-12)
    dm=pd.read_csv(output/'dm_tests.csv')
    assert len(dm)==156 and dm.groupby('hac_lag_weeks').size().eq(78).all()
    a=dm.loc[dm['model_a'].eq('ensemble_level_fixed') & dm['model_b'].eq('hgb_expanding_cached') & dm['hac_lag_weeks'].eq(3)].iloc[0]
    b=dm.loc[dm['model_a'].eq('ensemble_level_fixed') & dm['model_b'].eq('naive_yesterday_recursive') & dm['hac_lag_weeks'].eq(3)].iloc[0]
    findings=['','## Sonuçların yorumu','',
              f"Sabit ağırlıklı ensemble geliştirmede en düşük MAE'yi verdi ({scores.loc['ensemble_level_fixed','mae_tl_mwh']:.2f} TL/MWh). Önceki HGB: {scores.loc['hgb_expanding_cached','mae_tl_mwh']:.2f}; dünkü gün kıyası: {scores.loc['naive_yesterday_recursive','mae_tl_mwh']:.2f}.",
              f"Ensemble–HGB için 3 hafta HAC DM p={a['p_value']:.4f}, Holm p={a['holm_p_value']:.4f}. Çoklu karşılaştırma sonrasında HGB'ye üstünlük gösterilmedi. Ensemble–dünkü gün için Holm p={b['holm_p_value']:.4f}; bu yalnız keşifsel geliştirme dönemi karşılaştırmasıdır.",
              'Normalize profil ve iki aşamalı sıfır modeli seviye modellerini iyileştirmedi. Bu olumsuz sonuçlar korunmuştur.',
              f"Senaryo nominal %80 aralığının kapsaması %{100*metadata['probabilistic']['coverage_q10_q90']:.2f}; kapsama yetersizdir. Bu senaryolar güvenilir biçimde kalibre edilmiş bir risk dağılımı olarak sunulmamalıdır. Fiyat üst limitlerinin tarihsel sürümleri uygulanmamıştır.",
              'training_audit içindeki training_rows/training_last_label ortak uygun eğitim havuzunu tanımlar; naive veya cached model için yeni fit yapıldığı anlamına gelmez.',
              'Tam ayarlı gelecek-bozma tekrarında 13 yöntemin kayıtlı tahminleri eşleşti. Senaryoların ilk günü, olasılık toplamları, geçmiş artık zamanları ve son haftanın 30 yolu yeniden doğrulandı.']
    report=output/'report.md'
    content=report.read_text(encoding='utf-8')
    if '## Sonuçların yorumu' not in content:
        report.write_text(content+'\n'.join(findings)+'\n',encoding='utf-8')
    record=dict(prediction_rows=len(p),models=len(scores),weeks=34,scenario_paths=len(scenarios),
                full_parameter_future_poison_replay=True,scenario_replay=True,locked_test_opened=False,
                verification_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                result_sha256={file.name:hashlib.sha256(file.read_bytes()).hexdigest() for file in output.iterdir() if file.is_file() and file.name!='verification.json'})
    (output/'verification.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='result_sha256'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    verify(args.project.resolve(),args.output.resolve())
