"""Geliştirme tahminlerini aynı sabit uygulanabilir plan havuzunda karşılaştırır."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def score_decision(energy, fees, actual, forecast, reference, tolerance=.02):
    energy,fees,actual,forecast=map(lambda a:np.asarray(a,float),(energy,fees,actual,forecast))
    if energy.ndim!=2 or energy.shape[1]!=72 or fees.shape!=(energy.shape[0],) or actual.shape!=(72,) or forecast.shape!=(48,):
        raise ValueError('Plan/fiyat boyutları uyuşmuyor.')
    if not all(np.isfinite(a).all() for a in (energy,fees,actual,forecast)) or (energy<0).any():
        raise ValueError('Geçersiz plan/fiyat girdisi.')
    # Gelecek gerçek fiyatlar yalnız seçim sonrasında puanlamada kullanılır.
    expected=energy@np.r_[actual[:24],forecast]/1000+fees
    selected=int(np.argmin(expected))
    costs=energy@actual/1000+fees
    oracle=int(np.argmin(costs))
    potential=float(costs[reference]-costs[oracle])
    capture=float((costs[reference]-costs[selected])/potential) if potential>tolerance else np.nan
    return dict(selected=selected,oracle=oracle,reference_cost=float(costs[reference]),
                selected_cost=float(costs[selected]),oracle_cost=float(costs[oracle]),
                expected_cost=float(expected[selected]),regret=float(costs[selected]-costs[oracle]),
                advantage=float(costs[reference]-costs[selected]),potential=potential,capture=capture),costs


def parent_module(project):
    spec=importlib.util.spec_from_file_location('parent_walk_forward',project/'experiments/02_walk_forward/protocol.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def evaluate(project,output,config_file):
    if output.exists(): raise FileExistsError('Sonuç klasörü zaten var; üzerine yazılmaz.')
    config=json.loads(config_file.read_text(encoding='utf-8'))
    parent=parent_module(project)
    parent_out=project/config['parent_protocol']
    folds,lock=parent.verify_lock(project,project/'experiments/02_walk_forward/config.json',parent_out)
    development=folds.loc[folds['split'].eq('development')]
    locked_start=folds.loc[folds['split'].eq('locked_test'),'decision_origin'].min()
    if (parent_out/'locked_test').exists(): raise ValueError('Kilitli test açılmış; kapsam kontrol edilmeli.')
    forecast_out=project/config['forecast_results']
    verification=json.loads((forecast_out/'verification.json').read_text(encoding='utf-8'))
    for name,value in verification['result_sha256'].items():
        if digest(forecast_out/name)!=value: raise ValueError('Görev 3 sonucu değişmiş: '+name)
    info=json.loads((forecast_out/'experiment_info.json').read_text(encoding='utf-8'))
    for name,value in info['input_sha256'].items():
        if digest(project/name)!=value: raise ValueError('Görev 3 girdisi değişmiş: '+name)
    predictions=pd.read_csv(forecast_out/'predictions.csv',parse_dates=['decision_origin','target_time'])
    predictions=predictions.loc[predictions['model'].isin(config['models'])].copy()
    if set(predictions['decision_origin'])!=set(development['decision_origin']): raise ValueError('Geliştirme haftaları uyuşmuyor.')
    if predictions['target_time'].max()>=locked_start: raise ValueError('Kilitli hedefler kullanılamaz.')
    if predictions.duplicated(['decision_origin','target_time','model']).any(): raise ValueError('Tekrarlı tahmin.')
    sys.path.insert(0,str(project/'src'))
    from fiyat_tahmini import elektrik_fiyatlarini_oku
    from firma_cizelgeleme import firma_verisini_oku,maliyet_ve_ozet
    from ortak_plan_karsilastirmasi import arsivden_plan,tarihleri_tasi
    prices=elektrik_fiyatlarini_oku(project)
    prices=prices.loc[prices.index<locked_start]
    pool=project/config['plan_pool']
    index=pd.read_csv(pool/'plan_indeksi.csv')
    energy=np.load(pool/'saatlik_enerji.npy')
    fees=index['elektrik_disi_gider_tl'].to_numpy()
    ref_rows=index.index[index['diger_kaynaklar'].eq('referans')&index['H02_kaynagi'].eq('referans')&index['yukleme_kaynagi'].eq('referans')]
    if len(ref_rows)!=1 or len(index)!=19: raise ValueError('Beklenen referans/19 plan havuzu yok.')
    reference=int(ref_rows[0])
    firm=firma_verisini_oku(project)
    base_start=firm['tesis_takvimi']['tarih_saat'].min()
    files=[config_file,pool/'plan_indeksi.csv',pool/'saatlik_enerji.npy',pool/'ortak_planlar.zip',
           forecast_out/'predictions.csv',forecast_out/'verification.json',parent_out/'test_lock.json',parent_out/'folds.csv']
    files+=list(Path(__file__).parent.glob('*.py'))
    files+=list((project/'src').glob('*.py'))
    files+=list((project/'data/synthetic/firma_01').glob('*.csv'))
    hashes={str(p.relative_to(project)):digest(p) for p in files}
    prior=pd.read_csv(project/'data/results/karar_degerlendirme_01/haftalik_metrikler.csv',parse_dates=['karar_zamani'])
    prior=prior.loc[prior['model'].eq('son_yayinlanan_gun') & prior['karar_zamani'].isin(development['decision_origin'])].set_index('karar_zamani')
    rows=[];checks=0
    for week,frame in predictions.groupby('decision_origin',sort=True):
        times=pd.date_range(week,periods=72,freq='h');actual=prices.reindex(times).to_numpy()
        if set(frame['model'])!=set(config['models']): raise ValueError('Haftalık yöntemler eksik.')
        v=tarihleri_tasi(firm,week)
        v['fiyatlar']=pd.DataFrame({'tarih_saat':times,'PTF (TL/MWh)':actual})
        validated=set()
        for model in config['models']:
            f=frame.loc[frame['model'].eq(model)].sort_values('target_time')
            if not pd.DatetimeIndex(f['target_time']).equals(times[24:]): raise ValueError('Hedef saatleri eksik.')
            np.testing.assert_allclose(f['actual'],actual[24:],atol=1e-9,rtol=0)
            r,costs=score_decision(energy,fees,actual,f['prediction'].to_numpy(),reference,config['information_value_minimum_tl'])
            for position in {reference,r['selected'],r['oracle']}:
                if position in validated: continue
                plan,loads=arsivden_plan(pool,index.iloc[position]['plan_id'],week,base_start)
                summary=maliyet_ve_ozet(v,plan,loads)[-1]
                np.testing.assert_allclose(summary['Karşılaştırılan toplam maliyet (TL)'],costs[position],atol=.02,rtol=0)
                validated.add(position);checks+=1
            if model==config['reference_forecast']:
                old=prior.loc[week]
                if old['secilen_plan']!=index.iloc[r['selected']]['plan_id']: raise ValueError('Basit yöntem önceki deneyle eşleşmedi.')
                np.testing.assert_allclose(old['havuz_regret_tl'],r['regret'],atol=.02,rtol=0)
            rows.append(dict(decision_origin=week,model=model,selected_plan=index.iloc[r['selected']]['plan_id'],
                             pool_oracle_plan=index.iloc[r['oracle']]['plan_id'],
                             reference_cost_tl=r['reference_cost'],selected_actual_cost_tl=r['selected_cost'],
                             pool_oracle_cost_tl=r['oracle_cost'],expected_cost_tl=r['expected_cost'],
                             pool_regret_tl=r['regret'],reference_advantage_tl=r['advantage'],
                             pool_information_value_tl=r['potential'],information_capture=r['capture'],
                             mae_tl_mwh=float(np.abs(f['prediction'].to_numpy()-actual[24:]).mean()),independently_validated=True))
        print(f'Doğrulandı {week.date()}',flush=True)
    weekly=pd.DataFrame(rows)
    summary=weekly.groupby('model').agg(weeks=('decision_origin','nunique'),mae_tl_mwh=('mae_tl_mwh','mean'),
              mean_cost_tl=('selected_actual_cost_tl','mean'),mean_regret_tl=('pool_regret_tl','mean'),
              total_regret_tl=('pool_regret_tl','sum'),mean_advantage_tl=('reference_advantage_tl','mean'),
              mean_weekly_capture=('information_capture','mean'),median_weekly_capture=('information_capture','median'),
              defined_capture_weeks=('information_capture','count'))
    for model in summary.index:
        sub=weekly.loc[weekly['model'].eq(model)]
        denominator=sub['pool_information_value_tl'].sum()
        summary.loc[model,'total_information_capture']=sub['reference_advantage_tl'].sum()/denominator if denominator>config['information_value_minimum_tl'] else np.nan
    pivot=weekly.pivot(index='decision_origin',columns='model',values='selected_actual_cost_tl')
    pairs=[]
    for a,b in itertools.combinations(config['models'],2):
        delta=pivot[a]-pivot[b]
        pairs.append(dict(model_a=a,model_b=b,mean_a_minus_b_tl=delta.mean(),total_a_minus_b_tl=delta.sum(),
                          a_cheaper_weeks=int((delta<-.02).sum()),equal_weeks=int((delta.abs()<=.02).sum()),b_cheaper_weeks=int((delta>.02).sum())))
    pairs=pd.DataFrame(pairs)
    for name,value in hashes.items():
        if digest(project/name)!=value: raise ValueError('Girdi değişmiş: '+name)
    parent.verify_lock(project,project/'experiments/02_walk_forward/config.json',parent_out)
    output.mkdir(parents=True)
    weekly.to_csv(output/'weekly_decision_metrics.csv',index=False,encoding='utf-8-sig')
    summary.to_csv(output/'model_summary.csv',encoding='utf-8-sig')
    pairs.to_csv(output/'paired_cost_differences.csv',index=False,encoding='utf-8-sig')
    metadata=dict(scope=config['scope'],weeks=34,models=config['models'],plans=19,independent_checks=checks,
                  locked_test_evaluated=False,new_models_trained=False,new_MILP_solutions=False,input_sha256=hashes)
    (output/'experiment_info.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'config_snapshot.json').write_bytes(config_file.read_bytes())
    draw(summary,config,output)
    report(summary,pairs,metadata,output)
    print(summary.round(6).to_string(),flush=True)
    print(pairs.round(6).to_string(index=False),flush=True)


def draw(summary,config,output):
    labels=['Basit','Lasso-AR','HGB','Ensemble']
    values=summary.reindex(config['models'])
    fig,axes=plt.subplots(1,3,figsize=(12,4))
    for ax,column,title in zip(axes,['mae_tl_mwh','mean_regret_tl','total_information_capture'],
                                ['Fiyat MAE (TL/MWh)','Havuz regret (TL/hafta)','Toplam bilgi değeri yakalama']):
        ax.bar(labels,values[column],color=['#64748b','#0e7490','#c76b26','#406348'])
        ax.set_title(title,fontsize=10);ax.tick_params(axis='x',labelsize=9);ax.grid(axis='y',alpha=.2)
    fig.suptitle('34 geliştirme haftası — aynı 19 plan; tam MILP oracle değildir',fontsize=11)
    fig.tight_layout();fig.savefig(output/'decision_comparison.png',dpi=160);plt.close(fig)


def report(summary,pairs,metadata,output):
    lines=['# Görev 3 tahminlerinin geliştirme dönemindeki karar karşılaştırması','',
           'Yalnız 5 Ocak–24 Ağustos 2026 arasındaki 34 geliştirme haftası kullanıldı. Son 10 kilitli hafta puanlanmadı. Görev 4 başlatılmadı; yeni tahmin modeli veya MILP çözümü üretilmedi.','',
           'Regret = seçilen planın gerçek maliyeti − 19 plan içindeki gerçek minimum. Bilgi değeri yakalama = (referans − seçilen)/(referans − havuz minimumu). Bunlar tam MILP oracle metrikleri değildir. Lasso alpha=1, Görev 3 geliştirme MAE sonucundan sabitlendi; maliyet karşılaştırmasına göre yeniden seçilmedi.','',
           '| Yöntem | MAE | Ortalama regret TL | Toplam bilgi yakalama | Haftalık oran ortalaması | Tanımlı hafta |',
           '|---|---:|---:|---:|---:|---:|']
    for name,r in summary.iterrows():
        lines.append(f"| {name} | {r['mae_tl_mwh']:.2f} | {r['mean_regret_tl']:.2f} | {r['total_information_capture']:.4f} | {r['mean_weekly_capture']:.4f} | {int(r['defined_capture_weeks'])} |")
    lines+=['','## Yorumlama ve kontrol','',
            'Payda 0,02 TL veya altındaysa bilgi oranı tanımsızdır; sıfıra çevrilmez. Negatif oranlar kırpılmaz. Küçük paydalı kayıplar haftalık oran ortalamasını çok negatif yapabilir; toplam oranla aynı ölçü değildir.',
            'İlk günün açıklanmış fiyatı bütün yöntemlerde aynıdır. Sonraki 48 saat kayıtlı tahminlerden alınır. Gelecek gerçek fiyat yalnız seçilen planın puanlanması ve havuz-oracle hesabında kullanılır.',
            f"Referans, havuz-oracle ve seçilen planlar için {metadata['independent_checks']} benzersiz hafta-plan fiziksel/maliyet denetimi geçti. Matris maliyetleri bağımsız hesapla eşleşti. Basit yöntemin seçim ve regret değerleri Görev 1'in aynı haftalarıyla eşleşti.",'',
            '| A − B | Ortalama maliyet farkı TL/hafta | A daha ucuz | Eşit | B daha ucuz |','|---|---:|---:|---:|---:|']
    for _,r in pairs.iterrows(): lines.append(f"| {r['model_a']} − {r['model_b']} | {r['mean_a_minus_b_tl']:.2f} | {r['a_cheaper_weeks']} | {r['equal_weeks']} | {r['b_cheaper_weeks']} |")
    lines+=['','Bu geliştirme dönemi ve dar plan havuzu dışında ekonomik üstünlük çıkarımı yapılmaz. Görev 3 fiyat tahmini skorları burada bütün fabrikayı yeniden optimize eden bir deney olarak yorumlanamaz.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    args=parser.parse_args()
    evaluate(args.project.resolve(),args.output.resolve(),args.config.resolve())
