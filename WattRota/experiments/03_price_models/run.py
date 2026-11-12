"""Görev 3: yalnız geliştirme bölümünde modeller, DM ve artık-bootstrap senaryoları."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import lightgbm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, f1_score, mean_pinball_loss

from models import feature_pack, forecast_candidates, level_only
from forecast_stats import dm_hac, holm_adjust, residual_scenarios


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_parent(project):
    path = project / 'experiments/02_walk_forward/protocol.py'
    spec = importlib.util.spec_from_file_location('parent_walk_forward_protocol', path)
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    return parent


def run(project, output, config_file):
    if output.exists():
        raise FileExistsError('Çıktı zaten var; önceki sonuçlara yazılmaz.')
    sys.path.insert(0, str(project / 'src'))
    from fiyat_tahmini import elektrik_fiyatlarini_oku
    config = json.loads(config_file.read_text(encoding='utf-8'))
    parent = load_parent(project)
    parent_output = project / config['parent_protocol']
    folds, lock = parent.verify_lock(project, project/'experiments/02_walk_forward/config.json', parent_output)
    development = folds.loc[folds['split'].eq('development')]
    locked_start = folds.loc[folds['split'].eq('locked_test'), 'decision_origin'].min()
    if (parent_output / 'locked_test').exists():
        raise ValueError('Ana protokolün kilitli sonuçları açılmış; geliştirme iddiası tekrar incelenmeli.')
    prices = elektrik_fiyatlarini_oku(project)
    # Bu deneyin çalışma verisi kilitli haftaların fiyatlarını içermez.
    prices = prices.loc[prices.index < locked_start].copy()
    np.random.seed(config['seed'])
    cached_path = parent_output / 'development/predictions.csv'
    cached = pd.read_csv(cached_path, parse_dates=['decision_origin', 'target_time'])
    seal = json.loads((parent_output/'development/development_seal.json').read_text(encoding='utf-8'))
    if digest(cached_path) != seal['files']['predictions.csv']:
        raise ValueError('Önceki HGB tahminlerinin mührü uyuşmuyor.')
    input_files = list(Path(__file__).parent.glob('*.py')) + [config_file, Path(__file__).with_name('sources.json'), Path(__file__).with_name('requirements.txt')]
    input_files += [parent_output/'folds.csv', parent_output/'test_lock.json', cached_path]
    hashes = {str(p.relative_to(project)): digest(p) for p in input_files}
    residual_bank = []
    calibration_rows = []
    for origin in pd.date_range(config['calibration_start'], config['calibration_end'], freq='W-MON'):
        pack = feature_pack(prices, origin, config)
        predicted = level_only(pack, config)
        actual = prices.reindex(pack['target']).to_numpy()
        residual_bank.append(dict(origin=origin, available_at=pack['target'].max(), error=actual-predicted))
        for time, value, true in zip(pack['target'], predicted, actual):
            calibration_rows.append(dict(origin=origin, target_time=time, prediction=value, actual=true))
        print(f'Kalibrasyon {origin.date()}', flush=True)
    rows, audits, zeros, scenario_rows, scenario_audit, probabilistic = [], [], [], [], [], []
    for _, fold in development.iterrows():
        origin = fold['decision_origin']
        pack = feature_pack(prices, origin, config)
        candidates, pzero, diagnostics, daily_mean = forecast_candidates(pack, config)
        hgb = cached.loc[cached['decision_origin'].eq(origin) & cached['model'].eq('hgb_residual_expanding')].sort_values('target_time')
        if not pd.DatetimeIndex(hgb['target_time']).equals(pack['target']):
            raise ValueError('Önceki HGB kapsamı uyuşmuyor.')
        candidates['hgb_expanding_cached'] = hgb['prediction'].to_numpy()
        candidates['ensemble_level_fixed'] = np.mean([candidates[x] for x in config['ensemble_level_components']], axis=0)
        candidates['ensemble_profile_fixed'] = np.mean([candidates[x] for x in config['ensemble_profile_components']], axis=0)
        actual = prices.reindex(pack['target']).to_numpy()
        for name, predicted in candidates.items():
            for time, value, true in zip(pack['target'], predicted, actual):
                rows.append(dict(decision_origin=origin, target_time=time, model=name, prediction=value, actual=true))
        diagnostics_by_name = {d['model']: d['convergence_warnings'] for d in diagnostics}
        diagnostics_by_name['ensemble_level_fixed'] = sum(diagnostics_by_name.get(n, 0) for n in config['ensemble_level_components'])
        diagnostics_by_name['ensemble_profile_fixed'] = sum(diagnostics_by_name.get(n, 0) for n in config['ensemble_profile_components'])
        for name in candidates:
            audits.append(dict(decision_origin=origin, model=name,
                               history_start=config['history_start'], available_last=pack['known'].index.max(),
                               training_last_label=pack['meta'].loc[pack['train'], 'tarih_saat'].max(),
                               training_rows=int(pack['train'].sum()),
                               convergence_warnings=diagnostics_by_name.get(name, 0), seed=config['seed']))
        for time, p, true in zip(pack['target'], pzero, actual):
            zeros.append(dict(decision_origin=origin, target_time=time, p_zero=p, actual_zero=int(true==0), predicted_zero=int(p>=config['zero_threshold'])))
        available_errors = [r for r in residual_bank if r['available_at'] < pack['cutoff']]
        if not available_errors:
            raise ValueError('Senaryolar için önceden gerçekleşmiş OOS artık yok.')
        scenario, choices = residual_scenarios(candidates[config['scenario_model']],
                            pack['known'].reindex(pd.date_range(origin, periods=24, freq='h')).to_numpy(),
                            np.stack([r['error'] for r in available_errors]), config['scenario_count'], config['seed']+origin.toordinal())
        for scenario_id, trajectory in enumerate(scenario):
            scenario_rows.append(dict(decision_origin=origin, scenario_id=scenario_id, probability=1/config['scenario_count'],
                                      **{f'hour_{h}':float(value) for h,value in enumerate(trajectory)}))
        scenario_audit.append(dict(decision_origin=origin, residual_paths=len(available_errors),
                                   residual_last_target=max(r['available_at'] for r in available_errors),
                                   available_last=pack['known'].index.max(), scenario_count=len(scenario)))
        quantiles = np.quantile(scenario[:,24:], config['scenario_quantiles'], axis=0)
        for i, time in enumerate(pack['target']):
            probabilistic.append(dict(decision_origin=origin, target_time=time, actual=actual[i],
                                     **{f'q{int(100*q)}':quantiles[j,i] for j,q in enumerate(config['scenario_quantiles'])}))
        residual_bank.append(dict(origin=origin, available_at=pack['target'].max(), error=actual-candidates[config['scenario_model']]))
        print(f'Geliştirme {origin.date()} — {len(candidates)} yöntem', flush=True)
    predictions = pd.DataFrame(rows)
    audits = pd.DataFrame(audits)
    if set(predictions['decision_origin']) != set(development['decision_origin']) or predictions['target_time'].max() >= locked_start:
        raise ValueError('Geliştirme kapsamı hatalı.')
    if predictions.duplicated(['decision_origin','target_time','model']).any() or not predictions.groupby(['decision_origin','model']).size().eq(48).all():
        raise ValueError('Eksik/tekrarlı tahmin.')
    error = predictions['prediction']-predictions['actual']
    predictions['absolute_error']=error.abs()
    predictions['squared_error']=error**2
    summary = predictions.groupby('model').agg(mae_tl_mwh=('absolute_error','mean'), mse=('squared_error','mean'), hours=('prediction','size')).reset_index()
    summary['rmse_tl_mwh']=np.sqrt(summary.pop('mse'))
    summary['convergence_warnings']=summary['model'].map(audits.groupby('model')['convergence_warnings'].sum())
    summary=summary.sort_values(['mae_tl_mwh','model'])
    # Yakınsamayan adaylar seçim için uygun kabul edilmez; skorları yine raporlanır.
    eligible=summary.loc[summary['convergence_warnings'].eq(0)]
    winner=eligible.iloc[0]['model']
    weekly=predictions.groupby(['decision_origin','model'])['absolute_error'].mean().unstack('model')
    dm_rows=[]
    for lag in config['dm_hac_lags']:
        for a,b in itertools.combinations(sorted(weekly.columns),2):
            result=dm_hac((weekly[a]-weekly[b]).to_numpy(),lag)
            dm_rows.append(dict(model_a=a,model_b=b,hac_lag_weeks=lag,n_weeks=len(weekly),**result))
    dm=pd.DataFrame(dm_rows)
    for lag, group in dm.groupby('hac_lag_weeks'):
        dm.loc[group.index,'holm_p_value']=holm_adjust(group['p_value'])
    zero=pd.DataFrame(zeros)
    zero_report=dict(zero_hours=int(zero['actual_zero'].sum()), predicted_zero_hours=int(zero['predicted_zero'].sum()),
                     f1=float(f1_score(zero['actual_zero'],zero['predicted_zero'],zero_division=0)),
                     brier=float(brier_score_loss(zero['actual_zero'],zero['p_zero'])))
    probability=pd.DataFrame(probabilistic)
    probability_report=dict(coverage_q10_q90=float(((probability['actual']>=probability['q10'])&(probability['actual']<=probability['q90'])).mean()),
                            mean_interval_width=float((probability['q90']-probability['q10']).mean()))
    for q in config['scenario_quantiles']:
        probability_report[f'pinball_{q}']=float(mean_pinball_loss(probability['actual'],probability[f'q{int(100*q)}'],alpha=q))
    parent.verify_lock(project,project/'experiments/02_walk_forward/config.json',parent_output)
    for name,value in hashes.items():
        if digest(project/name)!=value:
            raise ValueError('Çalışma sırasında girdi değişti: '+name)
    output.mkdir(parents=True)
    tables={'predictions':predictions,'training_audit':audits,'model_scores':summary,'weekly_mae':weekly.reset_index(),
            'dm_tests':dm,'zero_predictions':zero,'scenario_prices':pd.DataFrame(scenario_rows),
            'scenario_audit':pd.DataFrame(scenario_audit),'probabilistic_forecasts':probability,
            'calibration_predictions':pd.DataFrame(calibration_rows)}
    for name,table in tables.items(): table.to_csv(output/f'{name}.csv',index=False,encoding='utf-8-sig')
    (output/'config_snapshot.json').write_bytes(config_file.read_bytes())
    metadata=dict(selected_model=winner,selection='development_MAE_only_excluding_nonconverged',weeks=len(development),
                  models=len(summary),test_evaluated=False,input_sha256=hashes,lightgbm_version=lightgbm.__version__,
                  zero_model=zero_report,probabilistic=probability_report,
                  parent_test_lock_sha256=digest(parent_output/'test_lock.json'),
                  external_features_used=False)
    (output/'experiment_info.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
    draw(summary,probability,output)
    report(summary,dm,metadata,output)
    print(summary.to_string(index=False),flush=True)
    print(json.dumps(metadata|{'input_sha256':'recorded'},ensure_ascii=True),flush=True)


def draw(summary,probability,output):
    fig,ax=plt.subplots(figsize=(10,6))
    ax.barh(summary['model'][::-1],summary['mae_tl_mwh'][::-1],color='#0e7490')
    ax.set(xlabel='MAE (TL/MWh)',title='34 geliştirme haftası — kilitli test açılmadı')
    ax.grid(axis='x',alpha=.2);fig.tight_layout();fig.savefig(output/'model_comparison.png',dpi=150);plt.close(fig)
    first=probability.loc[probability['decision_origin'].eq(probability['decision_origin'].min())]
    fig,ax=plt.subplots(figsize=(11,4))
    ax.fill_between(first['target_time'],first['q10'],first['q90'],alpha=.2,label='30 senaryo: %10–%90')
    ax.plot(first['target_time'],first['actual'],label='Gerçek fiyat')
    ax.plot(first['target_time'],first['q50'],label='Senaryo medyanı')
    ax.set(ylabel='TL/MWh',title='İlk geliştirme haftası — önceden bilinen OOS artıklarla senaryolar')
    ax.legend();fig.tight_layout();fig.savefig(output/'scenario_example.png',dpi=150);plt.close(fig)


def report(summary,dm,metadata,output):
    lines=['# Fiyat tahmini geliştirme — görev 3','',
           'Yalnız 34 geliştirme haftası kullanıldı. Kilitli son 10 hafta açılmadı. 2026 daha önce görülmüştür; sonuçlar yeni kör test değildir. Model/alpha seçimiyle aynı geliştirme dönemindeki skor ve p-değerleri keşifseldir.','',
           '## Yöntemler ve sınırlar','',
           '- LEAR tarzı yöntem: her saat ve gün ufku için ayrı standartlaştırılmış Lasso-AR. Bu, literatürdeki LEAR yaklaşımından esinlenen bağımsız uyarlamadır; orijinal AIC/asinh/dış değişkenli modelin birebir yeniden üretimi değildir.',
           '- Seviye ve profil hedefleri ayrı denendi. Tarihsel profil gerçek günlük ortalamaya bölünür; ileri günde gerçek ortalama kullanılmaz. Ayrı bir model günlük ortalamayı tahmin eder; profil yeniden normalize edilip bu tahminle ölçeklenir. Sıfıra yakın tarihsel ortalamalar için epsilon=1 TL/MWh kullanılır.',
           '- Dünkü aynı saat kıyası ikinci bilinmeyen gün için özyinelemelidir; henüz açıklanmamış dünkü gerçek fiyat kullanılmaz. Geçen hafta aynı saat ve 28 günlük hafta içi/sonu ortalamaları ayrıca raporlanır.',
           '- Karar örnekleri pazartesi başladığı için tahmin hedefleri salı/çarşambadır. Hafta içi/sonu yönteminin hafta sonu dalı birim testinde sınanır; bu 34 haftalık deney hafta sonu tahmin başarısını ölçmez.',
           '- Tatiller Diyanet ve 2429 sayılı kanun kaynaklarına dayalıdır. Yarım günler saat 13.00 sonrası işaretlenir. İdari izinler ve tesise özgü tatil/çalışma takvimi fiyat tahminine otomatik eklenmez.',
           '- LightGBM sıfır sınıflandırması + pozitif fiyat modeli ile iki aşamalı tahmin üretir. Sabit eşik 0,5. Ensemble ağırlıkları eşittir ve config içinde önceden sabittir.',
           '- EPİAŞ yük tahmini API denemesi kimliksiz HTTP 401 döndürdü. Yetkili TGT bulunmadığından yük/rüzgâr/güneş tahminleri ve yayımlanma anına ait tarihsel sürümleri edinilmedi. Gerçekleşmiş değerler yerine kullanılmadı. Dış değişken katkısı sınanmış sayılmaz.','',
           '## Geliştirme skorları','', '| Model | MAE | RMSE | Yakınsama uyarısı |','|---|---:|---:|---:|']
    for _,r in summary.iterrows(): lines.append(f"| {r['model']} | {r['mae_tl_mwh']:.2f} | {r['rmse_tl_mwh']:.2f} | {int(r['convergence_warnings'])} |")
    lines+=['',f"Geliştirme seçimi: **{metadata['selected_model']}**. Üretim maliyeti üstünlüğü ölçülmedi.",'',
            '## DM değerlendirmesi','',
            'Her karar haftasının 48 saatlik mutlak hataları ortalanır. DM, bu 34 eşleştirilmiş haftalık kayıp farkı üzerinde asimptotik normal dağılım ve Newey–West/Bartlett HAC (0 ve 3 hafta) ile hesaplanır. Saatler arası veya haftalar arasındaki boşluklar yapay biçimde kesintisiz 1.632 saat gibi ele alınmaz. Her HAC ayarı için bütün ikililere Holm düzeltmesi uygulanır. Küçük örneklem, model/alpha seçimi ve önceden görülmüş dönem nedeniyle sonuçlar keşifseldir; nihai test anlamlılığı değildir. Sıfır uzun dönem varyansında tanımsız durum gizlenmez.',
            'Bütün karşılaştırmalar `dm_tests.csv` dosyasındadır; negatif fark A tahmininin daha düşük kayıp verdiğini gösterir.','',
            '## Olasılıksal tahmin','',
            'Sabit LightGBM-seviye modeli için 2025 son çeyreğinin 12 haftasında gerçek zamanlı bilgi kesimli OOS tahminler üretildi. Her geliştirme haftasında yalnız daha önce gerçekleşmiş 48 saatlik artık yolları eklenir. 30 tam yol örneklenir; böylece yol içi saat ilişkisi korunur. İlk 24 saat her senaryoda açıklanmış fiyatla aynıdır. Negatif senaryo fiyatları sıfırda kırpılır. Bu ampirik artık bootstrap yaklaşımı rejim değişimlerini veya kuyruk risklerini garanti etmez.',
            f"%10–%90 aralığı kapsaması: {metadata['probabilistic']['coverage_q10_q90']:.3f}; ortalama genişlik: {metadata['probabilistic']['mean_interval_width']:.2f} TL/MWh. Nominal hedef %80; ölçülen kapsama bunun yerine kullanılır.",
            f"Sıfır tahmini F1: {metadata['zero_model']['f1']:.3f}; Brier: {metadata['zero_model']['brier']:.4f}; gerçek sıfır saat: {metadata['zero_model']['zero_hours']}; tahmin edilen sıfır saat: {metadata['zero_model']['predicted_zero_hours']}.",'',
            'Kaynak bağlantıları deney klasöründeki `sources.json` dosyasındadır. Eski config, kaynak ve sonuçlar değiştirilmedi.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    args=parser.parse_args()
    run(args.project.resolve(),args.output.resolve(),args.config.resolve())
