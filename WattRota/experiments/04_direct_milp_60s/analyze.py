"""Pilotları birleştirmeden karşılaştırır; MILP çözmez."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import text,bindparam
from sqlalchemy.dialects.postgresql import JSONB

from common import shift_firm,assert_prefix
from costs import cost_breakdown,ADDITIVE
from forecasting import forecasts_at
from run import write_json,tree_hashes


def read_plan(output,week,policy):
    key='oracle' if policy=='oracle_incumbent' else policy.replace('_open','_d0').replace('_rolling','_d2')
    folder=output/pd.Timestamp(week).strftime('%Y%m%d')/key
    return (pd.read_csv(folder/'plan.csv',keep_default_na=False,parse_dates=['tarih_saat']),
            pd.read_csv(folder/'loads.csv',parse_dates=['tarih_saat']))


def compare_schedules(a,b):
    machine_keys=['kaynak_id','tarih_saat']
    machine_fields=['durum','urun_id','is_emri_id']
    pa=a[0].set_index(machine_keys)[machine_fields].sort_index()
    pb=b[0].set_index(machine_keys)[machine_fields].sort_index()
    if not pa.index.equals(pb.index):raise AssertionError('Plan anahtarları farklı.')
    changed=int(pa.ne(pb).any(axis=1).sum())
    load_keys=['siparis_id','kaynak_id','tarih_saat']
    la=a[1].groupby(load_keys)['miktar_ton'].sum()
    lb=b[1].groupby(load_keys)['miktar_ton'].sum()
    index=la.index.union(lb.index)
    delta=(la.reindex(index,fill_value=0)-lb.reindex(index,fill_value=0)).abs()
    same_load=bool((delta<=1e-6).all())
    return dict(identical_machine_schedule=changed==0,identical_loading_schedule=same_load,
                identical_full_schedule=changed==0 and same_load,changed_machine_resource_hours=changed,
                loading_absolute_difference_ton=float(delta.sum()))


def clean(frame):
    return json.loads(json.dumps(database_records(frame),default=str,allow_nan=False))


def database_records(frame):
    return [{k:(None if pd.isna(v) else v) for k,v in row.items()} for row in frame.to_dict('records')]


def sql_analysis(engine,experiment_id,tables):
    from kod.db import db_transaction
    with db_transaction(engine,write=True) as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS results.milp_analysis_04 (experiment_id text NOT NULL, analysis text NOT NULL, row_no integer NOT NULL, payload jsonb NOT NULL, PRIMARY KEY (experiment_id,analysis,row_no))'))
        statement=text('INSERT INTO results.milp_analysis_04 VALUES (:id,:analysis,:row_no,:payload) ON CONFLICT (experiment_id,analysis,row_no) DO UPDATE SET payload=EXCLUDED.payload WHERE results.milp_analysis_04.payload IS DISTINCT FROM EXCLUDED.payload').bindparams(bindparam('payload',type_=JSONB))
        records=[dict(id=experiment_id,analysis=name,row_no=i,payload=r) for name,frame in tables.items() for i,r in enumerate(clean(frame))]
        conn.execute(statement,records)
        query=text('SELECT analysis,row_no,payload FROM results.milp_analysis_04 WHERE experiment_id=:id ORDER BY analysis,row_no')
        first=conn.execute(query,{'id':experiment_id}).all()
        conn.execute(statement,records)
        assert first==conn.execute(query,{'id':experiment_id}).all()
        assert len(first)==len(records)
        summary_statement=text('INSERT INTO results.milp_summary_04 VALUES (:id,:policy,:payload) ON CONFLICT (experiment_id,policy) DO UPDATE SET payload=EXCLUDED.payload WHERE results.milp_summary_04.payload IS DISTINCT FROM EXCLUDED.payload').bindparams(bindparam('payload',type_=JSONB))
        summaries=[dict(id=experiment_id,policy=r['policy'],payload=r) for r in clean(tables['policy_summary'])]
        conn.execute(summary_statement,summaries)
        query=text('SELECT policy,payload FROM results.milp_summary_04 WHERE experiment_id=:id ORDER BY policy')
        before=conn.execute(query,{'id':experiment_id}).all();conn.execute(summary_statement,summaries)
        assert before==conn.execute(query,{'id':experiment_id}).all() and len(before)==8
    return len(records)


def analyze(project,output):
    started=time.perf_counter()
    sys.path.insert(0,str(project));sys.path.insert(0,str(project/'src'))
    from kod.db import create_db_engine,read_firm,read_prices
    from firma_cizelgeleme import maliyet_ve_ozet
    from storage import snapshot,upload
    info=json.loads((output/'pilot_info.json').read_text(encoding='utf-8'))
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    config=json.loads((output/'config_snapshot.json').read_text(encoding='utf-8'))
    old=project/config['previous_pilot']
    runs=pd.read_csv(output/'solver_runs.csv',parse_dates=['week'],float_precision='round_trip')
    weekly=pd.read_csv(output/'weekly_metrics.csv',parse_dates=['week'],float_precision='round_trip')
    previous=pd.read_csv(old/'weekly_metrics.csv',parse_dates=['week'],float_precision='round_trip')
    old_runs=pd.read_csv(old/'solver_runs.csv',parse_dates=['week'],float_precision='round_trip')
    summary=pd.read_csv(output/'policy_summary.csv',float_precision='round_trip')
    parts=pd.read_csv(output/'policy_cost_components.csv',parse_dates=['week'],float_precision='round_trip')
    assert len(runs)==40 and len(weekly)==32 and len(summary)==8
    assert runs.groupby('week').size().eq(10).all()
    assert runs['time_limit_seconds'].eq(60).all()
    assert runs['effective_seed'].eq(42).all() and runs['seed_option_accepted'].all()
    assert np.isclose(runs['solver_objective_tl'],runs['expected_cost_tl'],atol=.02,rtol=0).all()
    np.testing.assert_allclose(parts[ADDITIVE].sum(axis=1),parts['total_cost_tl'],atol=.02,rtol=0)
    comparison=previous.merge(weekly,on=['week','policy'],suffixes=('_15s','_60s'),how='outer',validate='one_to_one')
    comparison['saving_from_60s_tl']=comparison['actual_cost_tl_15s']-comparison['actual_cost_tl_60s']
    comparison['paired_available']=comparison['actual_cost_tl_15s'].notna()&comparison['actual_cost_tl_60s'].notna()
    schedules=[];ml=[];budget_schedules=[]
    for week in sorted(weekly['week'].unique()):
        for mode in ('open','rolling'):
            for budget,folder in [(15,old),(60,output)]:
                f=(previous if budget==15 else weekly).loc[lambda x:x['week'].eq(week)].set_index('policy')
                difference=float(f.loc['hgb_'+mode,'actual_cost_tl']-f.loc['ensemble_'+mode,'actual_cost_tl'])
                schedules.append(dict(week=week,mode=mode,seconds=budget,hgb_minus_ensemble_tl=difference,
                    identical_cost_within_002_tl=abs(difference)<=.02,
                    **compare_schedules(read_plan(folder,week,'hgb_'+mode),read_plan(folder,week,'ensemble_'+mode))))
            for source in ('hgb','ensemble'):
                frame=weekly.loc[weekly['week'].eq(week)].set_index('policy')
                ml.append(dict(week=week,mode=mode,source=source,
                     naive_cost_tl=float(frame.loc['naive_'+mode,'actual_cost_tl']),
                     ml_cost_tl=float(frame.loc[source+'_'+mode,'actual_cost_tl']),
                     naive_minus_ml_tl=float(frame.loc['naive_'+mode,'actual_cost_tl']-frame.loc[source+'_'+mode,'actual_cost_tl']),
                     **compare_schedules(read_plan(output,week,'naive_'+mode),read_plan(output,week,source+'_'+mode))))
                budget_schedules.append(dict(week=week,policy=source+'_'+mode,
                     **compare_schedules(read_plan(old,week,source+'_'+mode),read_plan(output,week,source+'_'+mode))))
        budget_schedules.append(dict(week=week,policy='oracle_incumbent',
              **compare_schedules(read_plan(old,week,'oracle_incumbent'),read_plan(output,week,'oracle_incumbent'))))
    schedules=pd.DataFrame(schedules);ml=pd.DataFrame(ml)
    paired_runs=old_runs.merge(runs,on=['week','run_key'],suffixes=('_15s','_60s'),validate='one_to_one')
    paired_runs['same_initial_decision_problem']=paired_runs['decision_day_60s'].eq(0)
    paired_runs['actual_cost_improvement_tl']=paired_runs['actual_cost_tl_15s']-paired_runs['actual_cost_tl_60s']
    paired_runs['gap_change_60s_minus_15s']=paired_runs['mip_gap_60s']-paired_runs['mip_gap_15s']
    seed_proposal=json.loads((output/'sensitivity_proposal.json').read_text(encoding='utf-8'))
    engine=create_db_engine(project)
    try:
        firm=read_firm(engine);prices=read_prices(engine);verified=0;checks=0;warm_checks=0
        for week,rows in runs.groupby('week'):
            v=shift_firm(firm,week);actual=prices.reindex(pd.date_range(week,periods=72,freq='h'))
            v['fiyatlar']=pd.DataFrame({'tarih_saat':actual.index,'PTF (TL/MWh)':actual.to_numpy()})
            continuation={}
            from common import signature
            reference_signature=signature(v['referans_plan'],v['referans_yuklemeler'],week)
            for row in rows.itertuples(index=False):
                policy='oracle_incumbent' if row.source=='oracle' else row.run_key.replace('_d0','_open').replace('_d2','_rolling')
                folder=output/week.strftime('%Y%m%d')/row.run_key
                plan=pd.read_csv(folder/'plan.csv',keep_default_na=False,parse_dates=['tarih_saat'])
                loads=pd.read_csv(folder/'loads.csv',parse_dates=['tarih_saat'])
                result=maliyet_ve_ozet(v,plan,loads)
                assert abs(float(result[-1]['Karşılaştırılan toplam maliyet (TL)'])-row.actual_cost_tl)<.02
                cost_breakdown(v,result);verified+=1
                current=(plan,loads,result[0])
                if row.decision_day==0:
                    assert row.warm_start=='initial_postgresql_reference' and row.warm_start_signature==reference_signature
                else:
                    before=continuation[row.source]
                    assert row.warm_start_signature==signature(before[0],before[1],week)
                    assert_prefix(before,current,week+pd.Timedelta(days=row.decision_day))
                warm_checks+=1
                if row.source!='oracle':
                    continuation[row.source]=current
                    planning=pd.read_csv(folder/'planning_prices.csv',parse_dates=['tarih_saat'])
                    cut=(row.decision_day+1)*24
                    np.testing.assert_allclose(planning['PTF (TL/MWh)'].iloc[:cut],actual.iloc[:cut],atol=1e-9,rtol=0);checks+=1
                    if row.source!='naive':
                        previous_price=pd.read_csv(old/week.strftime('%Y%m%d')/row.run_key/'planning_prices.csv')
                        np.testing.assert_allclose(planning['PTF (TL/MWh)'],previous_price['PTF (TL/MWh)'],atol=1e-9,rtol=0)
        origin=runs['week'].min();cut=origin+pd.Timedelta(days=1)
        known=prices.loc[prices.index<cut].copy()
        future=prices.loc[prices.index<origin+pd.Timedelta(days=3)].copy();future.loc[future.index>=cut]=1e9
        a,_=forecasts_at(known,origin,project,config);b,_=forecasts_at(future,origin,project,config)
        for source in config['forecast_sources']:np.testing.assert_array_equal(a[source].to_numpy(),b[source].to_numpy())
        np.testing.assert_array_equal(a['naive'].to_numpy(),np.tile(known.iloc[-24:].to_numpy(),2))
        old_sql=snapshot(engine,info['previous_experiment_id'])
        original_sql=snapshot(engine,info['experiment_id'])
        upload(engine,info['experiment_id'],database_records(runs),database_records(weekly));first=snapshot(engine,info['experiment_id'])
        assert original_sql==first
        upload(engine,info['experiment_id'],database_records(runs),database_records(weekly));assert first==snapshot(engine,info['experiment_id'])
        assert old_sql==snapshot(engine,info['previous_experiment_id'])
        tables={'policy_summary':summary,'policy_cost_components':parts,'budget_comparison':comparison,
                'hgb_ensemble_schedules':schedules,'ml_vs_naive':ml,'budget_schedules':pd.DataFrame(budget_schedules),
                'solver_budget_comparison':paired_runs}
        for name,frame in tables.items():frame.to_csv(output/f'{name}.csv',index=False,encoding='utf-8-sig')
        sql_rows=sql_analysis(engine,info['experiment_id'],tables)
        if tree_hashes(project,[old,project/config['previous_module']])!=manifest['preserved_files']:
            raise AssertionError('Eski deney dosyaları değişti.')
        result=dict(saved_solutions_revalidated=verified,known_price_prefixes_checked=checks,warm_start_checks=warm_checks,
                    future_poison_model_tests=3,naive_matches_previous_definition=True,forecast_prices_same_as_15s=True,
                    sql_idempotent=True,sql_analysis_rows=sql_rows,sql_summary_rows=8,seed_option_verified_in_40_runs=True,
                    postprocessing_seconds=time.perf_counter()-started,old_experiment_preserved=True)
        write_json(output/'review_checks.json',result)
        report(output,info,summary,comparison,schedules,ml,runs,paired_runs,parts,seed_proposal,result)
        draw(output,summary,comparison,ml)
        write_json(output/'analysis_manifest.json',dict(experiment_id=info['experiment_id'],milp_reruns=0,
              source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
              note='Postprocessing only; original solve manifest unchanged.'))
        print(json.dumps(result),flush=True)
        print(summary.round(4).to_string(index=False),flush=True)
    finally:engine.dispose()


def markdown(frame,columns):
    lines=['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    for _,row in frame.iterrows():
        values=[]
        for c in columns:
            x=row[c]
            if pd.isna(x):values.append('tanımsız')
            elif isinstance(x,(float,np.floating)):values.append(f'{x:.4f}' if 'capture' in c else f'{x:.2f}')
            else:values.append(str(x))
        lines.append('| '+' | '.join(values)+' |')
    return '\n'.join(lines)


def report(output,info,summary,comparison,schedules,ml,runs,paired_runs,parts,proposal,checks):
    quality=paired_runs.loc[paired_runs['same_initial_decision_problem']]
    oracle=runs.loc[runs['source'].eq('oracle')]
    delta=comparison.loc[comparison['paired_available']].groupby('policy',as_index=False)['saving_from_60s_tl'].sum()
    ml_sum=ml.groupby(['mode','source'],as_index=False).agg(naive_minus_ml_tl=('naive_minus_ml_tl','sum'),
                weeks_ml_cheaper=('naive_minus_ml_tl',lambda x:int((x>.02).sum())),
                weeks_same_cost=('naive_minus_ml_tl',lambda x:int((x.abs()<=.02).sum())),
                weeks_naive_cheaper=('naive_minus_ml_tl',lambda x:int((x<-.02).sum())))
    identical=schedules.groupby('seconds',as_index=False).agg(identical_full_schedules=('identical_full_schedule','sum'),comparisons=('identical_full_schedule','size'),identical_machine_schedules=('identical_machine_schedule','sum'),identical_costs=('identical_cost_within_002_tl','sum'))
    cost_sum=parts.groupby('policy',as_index=False)[ADDITIVE+['total_electricity_tl','total_cost_tl']].sum()
    text_lines=['# WattRota — 60 saniyelik dört haftalık doğrudan MILP pilotu','',
      f"Deney: `{info['experiment_id']}`. Önceki deney: `{info['previous_experiment_id']}`. Girdiler PostgreSQL okuma katmanından alındı; hash'ler önceki deneyle eşleşti. Haftalar: 5 Ocak, 23 Mart, 8 Haziran ve 24 Ağustos 2026.",'',
      '## Protokol ve doğrulama','',
      'Her hafta bir oracle ve üç yöntem için d0/d1/d2 çözümü: 10 MILP; toplam 40. Gap hedefi 0,001; tek thread; seed 42; yerel arama kapalı; her çözüm en fazla 60 saniye. Açık döngü ve rolling ilk kararı ortaktır. Fiyattan bağımsız referans çözülmez; uygun plan olarak değerlendirilir. Naive, önceki son_yayinlanan_gun yöntemidir; açıklanmış günün profilini sonraki iki gün için tekrarlar.','',
      'İlk çözümlerin warm startı aynı PostgreSQL referansıdır. Önceki 15 saniyelik planlar kullanılmadı. Rolling yalnız kendi yönteminin önceki gün planıyla devam eder; uygulanmış saatler, stok, ayar, hazırlık ve minimum süre geçmişi sabitlenir. Her gün yalnız 24 saat uygulanır. Kalan son gün bütünüyle açıklanmış olduğundan d2 tahmin gerektirmez.','',
      'Her çözümün solver_objective_tl ve lower_bound_tl alanları o koşumun planlama fiyatlarına göredir. actual_cost_tl aynı planın gerçek fiyatlarla yeniden hesaplanan maliyetidir. Tahminli çözümün alt sınırı, gerçek fiyatlı regret hesabında kullanılmaz; bu hesap yalnız oracle alt sınırını kullanır.','',
      f"40 plan bağımsız doğrulandı ve diskten yeniden doğrulandı. İhlal: 0. Warm-start denetimi: {checks['warm_start_checks']}; bilinen fiyat öneki: {checks['known_price_prefixes_checked']}; gerçek model hattında gelecek fiyatlarını bozma testi: üç yöntem. PostgreSQL çift yükleme içerik/sayı eşitliği geçti. 40 koşum + 32 haftalık politika + 8 yöntem özeti ayrı deney kimliğiyle saklandı. Eski deney dosyaları ve SQL kayıtları korundu.",'',
      '## Gerçekleşen maliyet ve oracle belirsizliği','',
      markdown(summary,['policy','total_savings_tl','mean_actual_cost_tl','mean_oracle_incumbent_gap_tl','mean_regret_lower_tl','mean_regret_upper_tl','capture_vs_incumbent']), '',
      'Tasarruf referans eksi politika maliyetidir. Negatif tasarruf gerçek fiyatlarla daha pahalı plan demektir. Oracle plana göre ham fark, kesin optimuma göre gerçek regret değildir. Oracle alt sınırı L ve bulunan uygun plan U için C* ∈ [L,U]; gerçek regret ∈ [max(0,C−U), max(0,C−L)]. Oracle sertifikalanmadıkça noktasal gerçek regret raporlanmaz. Bulunan oracle plandan daha ucuz bir tahminli plan, geçerli bir gözlemdir; negatif gerçek regret anlamına gelmez.','',
      f"Kesin oracle sertifikası: {info['exact_oracle_weeks']}/4. Oracle MIP gap aralığı: {oracle['mip_gap'].min():.5f}–{oracle['mip_gap'].max():.5f}. Süre sınırına ulaşan koşum: {int(runs['time_limit_reached'].sum())}/40. HiGHS 'Optimal' durumu yalnız göreli gap toleransına ulaşmış olabilir; kesin optimum diye adlandırılmaz.",'',
      'Bilgi yakalama, toplam kazanç / toplam (referans−oracle bulunan plan) olarak hesaplanır; haftalık oran ortalaması alınmaz. Sıfır payda tanımsız bırakılır. Oracle optimumu kesin değilse bu bulunan plana göre oran da geçicidir. Gerçek oranın alt/üst sınırları policy_summary.csv içinde ayrıca tutulur. Gözlenen iki geçerli planın maliyet farkı hesaplanabilir; bu farkın gözlenmesi optimumun bilinmesini gerektirmez.','',
      '## 15 ve 60 saniye karşılaştırması','',
      markdown(delta,['policy','saving_from_60s_tl']),'',
      'Pozitif değer, aynı dört hafta/politikada 60 saniyelik koşumun toplam gerçek maliyetinin daha düşük olduğunu gösterir. İki deneyin en iyi planları birleştirilmedi. Naive 15 saniyelik deneyde olmadığından onun için süre karşılaştırması yapılamaz. Detay: budget_comparison.csv ve budget_schedules.csv.','',
      f"Aynı başlangıç karar problemlerinde (oracle ve HGB/ensemble d0, 12 eşleşme) ortalama gap: 15 s {quality['mip_gap_15s'].mean():.5f}, 60 s {quality['mip_gap_60s'].mean():.5f}. Rolling d1/d2, farklı geçmiş planlar nedeniyle farklı kalan uygun çözüm kümelerine sahip olabilir; bu alt sınırlar aynı problemin iyileşmesi gibi yorumlanmaz.",'',
      '## HGB ve ensemble: maliyet mi, çizelge mi aynı?','',
      markdown(identical,['seconds','identical_costs','identical_full_schedules','comparisons','identical_machine_schedules']),'',
      'Her süre için dört hafta × iki politika = sekiz karşılaştırma. Tam eşitlik hem kaynak/saat faaliyetlerini (ürün ve iş emri dahil), hem sipariş/kaynak/saat yükleme miktarlarını gerektirir; yükleme toleransı 10⁻⁶ ton. Aynı maliyet, aynı çizelge varsayılmadı. Ayrıntı: hgb_ensemble_schedules.csv.','',
      '## Basit yönteme karşı ML','',
      markdown(ml_sum,['mode','source','naive_minus_ml_tl','weeks_ml_cheaper','weeks_same_cost','weeks_naive_cheaper']),'',
      'Pozitif değer ML planının basit yöntemden daha ucuz olduğunu, negatif değer basit yöntemin daha ucuz olduğunu gösterir. Bu, dört haftanın sabit seed/süre koşullarındaki gözlenen farkıdır. Rolling avantajı doğrudan ML katkısı değildir: yeni açıklanan fiyatların ve ek çözüm bütçesinin etkisi henüz ayrıştırılmamıştır. Yöntem farklarının çözücü seedlerine dayanıklılığı da bu pilotla kanıtlanmaz.','',
      '## Maliyet kalemleri','',
      markdown(cost_sum,['policy']+ADDITIVE+['total_cost_tl']),'',
      'Operating electricity: üretim, yükleme ve temel yük elektriği. Startup electricity: açılış ek enerjisi. Transition electricity: hazırlık sırasındaki enerji. Son iki olayın elektrik dışı giderleri ayrı sütunlardır. Bu altı kalem toplanır; total_electricity_tl ilk üç elektrik sütununun toplamıdır, ikinci kez eklenmez. Plan değişikliği modelde sıfır TL/kaynak-saat parametresiyle bulunur; sıfır korunmuştur. Saatlik kalemler bağımsız doğrulayıcı maliyetine eşleştirildi.','',
      '## Ölçülen süre ve kapsam','',
      f"40 MILP pilotu: {info['total_pilot_seconds']/60:.2f} dakika. Son kontrol/raporlama: {checks['postprocessing_seconds']/60:.2f} dakika (MILP içermez). Üç tahmin yöntemli 34 hafta, 340 MILP için ölçülen hafta ortalamasından tahmin: {info['estimated_34_weeks_minutes']:.2f} dakika. Gözlenen en kısa/uzun haftanın ölçeklenmesi: {info['observed_min_max_scaled_to_34_minutes']} dakika; güven aralığı değildir. Sadece çözücü limitlerinin toplam üst bütçesi 340 dakikadır; hazırlama/tahmin/doğrulama ayrıca zaman alır.",'',
      '34 hafta, kilitli test, duyarlılık deneyi, Görev 5 ve stokastik mod çalıştırılmadı. Commit için kullanıcı onayı gerekir.','',
      '## Önerilen çözücü duyarlılık deneyi — çalıştırılmadı','',
      f"Önceden yazılan seçim kuralı: geliştirme döneminin içinden yaklaşık eşit aralıklı fold 5, 16, 28. Tarihler: {proposal['weeks']}. Seed'ler: {proposal['seeds']}. Bu seçim maliyet sonuçlarına göre yapılmadı; geliştirme verisinin daha önce görülmüş olduğu gerçeğini değiştirmez. Onayla sabitlenecek protokol: üç hafta × beş seed × (oracle + naive/HGB/ensemble açık döngü) = 60 MILP; her biri 60 saniye; rolling eklenmez. Tüm seed sonuçları raporlanır, en iyi seed seçilmez. Maliyet/gap dağılımı, plan eşitliği ve ML−naive farkının işaret kararlılığı incelenir.",'',
      'HiGHS random_seed seçeneği her çözümde setOptionValue ile atanıp getOptionValue ile geri okundu; kabul durumu ve etkili seed 42 tüm 40 kayıtta doğrulandı. Bu yalnız config alanı değildir. Ancak seed değiştirildiğinde sonuçların gerçekten ne kadar değiştiği henüz deneyle ölçülmedi.','',
      '## Stokastik mod','',
      'Önceki senaryo kapsaması %61,89 olduğu için henüz önerilmez. Önce deterministik çözüm kalitesi ve seed duyarlılığı anlaşılmalı. Tek sabit çizelgede doğrusal senaryo ortalama maliyeti yalnız ortalama fiyatla çözmeye eşdeğerdir; ek değer iddiası için kalibrasyon ve recourse veya risk hedefi gerekir.']
    (output/'report.md').write_text('\n'.join(text_lines)+'\n',encoding='utf-8')


def draw(output,summary,comparison,ml):
    fig,axes=plt.subplots(2,1,figsize=(11,9),layout='constrained')
    s=summary.set_index('policy')['total_savings_tl']
    s.reindex(['naive_open','hgb_open','ensemble_open','naive_rolling','hgb_rolling','ensemble_rolling']).plot.barh(ax=axes[0])
    axes[0].set(title='60 saniye — dört haftada referansa göre toplam tasarruf',xlabel='TL');axes[0].axvline(0,color='black',lw=.8)
    g=ml.groupby(['mode','source'])['naive_minus_ml_tl'].sum();g.plot.barh(ax=axes[1],color='darkorange')
    axes[1].set(title='Basit yöntem maliyeti − ML maliyeti',xlabel='TL; pozitif değer ML lehine');axes[1].axvline(0,color='black',lw=.8)
    fig.savefig(output/'pilot_comparison.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();analyze(args.project.resolve(),args.output.resolve())
