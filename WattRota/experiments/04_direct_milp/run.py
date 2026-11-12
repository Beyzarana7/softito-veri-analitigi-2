"""PostgreSQL girdileriyle dört haftalık doğrudan MILP ve günlük yeniden planlama pilotu."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import io
from zipfile import ZipFile

import numpy as np
import pandas as pd

from forecasting import forecasts_at,planning_prices,load_module
from metrics import decision_metrics,aggregate_capture


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shift_firm(firm,week):
    result=copy.deepcopy(firm)
    shift=pd.Timestamp(week)-firm['tesis_takvimi']['tarih_saat'].min()
    for frame in result.values():
        for column in frame:
            if pd.api.types.is_datetime64_any_dtype(frame[column]):frame[column]+=shift
    return result


def signature(plan,loads,start):
    p=plan.copy();y=loads.copy()
    for frame in (p,y):
        frame['tarih_saat']=((pd.to_datetime(frame['tarih_saat'])-pd.Timestamp(start))/pd.Timedelta(hours=1)).astype(int)
    p=p.sort_values(['kaynak_id','tarih_saat']).reset_index(drop=True)
    y['miktar_ton']=y['miktar_ton'].astype(float).round(6)
    y=y.sort_values(['siparis_id','kaynak_id','tarih_saat']).reset_index(drop=True)
    return hashlib.sha256((p.to_csv(index=False)+y.to_csv(index=False)).encode()).hexdigest()


def old_pool_signatures(project):
    # Yalnız sonuç yenilik denetimi; havuz çözücüye/amaç fonksiyonuna verilmez.
    signatures=set()
    with ZipFile(project/'data/results/ortak_plan_deneyi/ortak_planlar.zip') as archive:
        ids=sorted(set(n.split('/')[0] for n in archive.namelist()))
        for pid in ids:
            p=pd.read_csv(io.BytesIO(archive.read(pid+'/plan.csv')),keep_default_na=False)
            y=pd.read_csv(io.BytesIO(archive.read(pid+'/yuklemeler.csv')))
            signatures.add(signature(p,y,pd.to_datetime(p['tarih_saat']).min()))
    return signatures


def assert_prefix(previous,current,boundary):
    for a,b,keys in [(previous[0],current[0],['kaynak_id','tarih_saat']),
                     (previous[1],current[1],['siparis_id','kaynak_id','tarih_saat'])]:
        a=a.loc[a['tarih_saat']<boundary].sort_values(keys).reset_index(drop=True)
        b=b.loc[b['tarih_saat']<boundary].sort_values(keys).reset_index(drop=True)
        if 'miktar_ton' in a:
            a['miktar_ton']=a['miktar_ton'].astype(float)
            b['miktar_ton']=b['miktar_ton'].astype(float)
        pd.testing.assert_frame_equal(a,b,check_exact=False,atol=1e-7,rtol=0)
    a=previous[2].loc[previous[2]['tarih_saat']<boundary].reset_index(drop=True)
    b=current[2].loc[current[2]['tarih_saat']<boundary].reset_index(drop=True)
    pd.testing.assert_frame_equal(a,b,check_exact=False,atol=1e-6,rtol=0)


def save_run(folder,result,price_frame,real_hourly,row):
    folder.mkdir(parents=True)
    for name,frame in [('plan',result[0]),('loads',result[1]),('stocks',result[2]),
                       ('planning_prices',price_frame),('actual_hourly_cost',real_hourly)]:
        frame.to_csv(folder/f'{name}.csv',index=False,encoding='utf-8-sig')
    (folder/'run.json').write_text(json.dumps(row,default=str,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def pilot(project,output,config_file):
    overall_start=time.perf_counter()
    if output.exists():raise FileExistsError('Pilot klasörü zaten var; sonuçlar tekrar çözülerek karıştırılmaz.')
    sys.path.insert(0,str(project));sys.path.insert(0,str(project/'src'))
    from kod.db import create_db_engine,read_firm,read_prices
    from firma_cizelgeleme import maliyet_ve_ozet
    from solver import solve
    from storage import upload,snapshot
    config=json.loads(config_file.read_text(encoding='utf-8'))
    if config['phase']!='four_week_pilot_only' or len(config['pilot_fold_indices'])!=4 or config['stochastic_mode'] or config['locked_test_allowed']:
        raise ValueError('Bu komut yalnız dört haftalık deterministik pilot içindir.')
    if config['seed']!=42 or config['solver_threads']!=1 or config['local_search']:
        raise ValueError('Doğrulanmış tek iş parçacıklı sabit seed/tek arama ayarı korunmalı.')
    if config['solver_time_limit_seconds']<=0:raise ValueError('Her MILP için pozitif süre sınırı gerekli.')
    parent=load_module(project/'experiments/02_walk_forward/protocol.py','task4_protocol')
    parent_output=project/config['parent_protocol']
    folds,lock=parent.verify_lock(project,project/config['hgb_config'],parent_output)
    development=folds.loc[folds['split'].eq('development')].reset_index(drop=True)
    weeks=development.iloc[config['pilot_fold_indices']]['decision_origin'].tolist()
    if len(set(weeks))!=4:raise ValueError('Pilot haftaları benzersiz olmalı.')
    locked_start=folds.loc[folds['split'].eq('locked_test'),'decision_origin'].min()
    if (parent_output/'locked_test').exists():raise ValueError('Kilitli test sonucu mevcut; kapsam yeniden incelenmeli.')
    engine=create_db_engine(project)
    try:
        firm=read_firm(engine);prices=read_prices(engine)
        # Kilitli dönem modellerin/çözücülerin çalışma fiyat serisine hiç verilmez.
        prices=prices.loc[prices.index<locked_start].copy()
        input_hashes={name:hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest() for name,frame in firm.items()}
        input_hashes['postgresql_price_history']=hashlib.sha256(prices.to_csv().encode()).hexdigest()
        source_files=list(Path(__file__).parent.glob('*.py'))+[config_file,project/config['hgb_config'],project/config['ensemble_config']]
        source_hashes={str(p.relative_to(project)):digest(p) for p in source_files}
        exp_id='pilot04_'+hashlib.sha256(json.dumps([config,input_hashes,source_hashes],sort_keys=True).encode()).hexdigest()[:16]
        pool=old_pool_signatures(project)
        output.mkdir(parents=True)
        (output/'config_snapshot.json').write_bytes(config_file.read_bytes())
        (output/'manifest.json').write_text(json.dumps(dict(experiment_id=exp_id,phase='pilot',weeks=[str(w) for w in weeks],
             inputs='PostgreSQL via kod.db',input_hashes=input_hashes,source_hashes=source_hashes,
             locked_test_evaluated=False,stochastic_mode=False),ensure_ascii=False,indent=2),encoding='utf-8')
        run_rows=[];week_rows=[];times=[];boundaries=[];failures=[]
        setup_seconds=time.perf_counter()-overall_start
        for week in weeks:
            week_start=time.perf_counter();forecast_seconds=0.
            actual=prices.reindex(pd.date_range(week,periods=72,freq='h'))
            if actual.isna().any() or actual.index.max()>=locked_start:raise ValueError('Pilot fiyatları eksik/kilitli.')
            actual_firm=shift_firm(firm,week)
            actual_firm['fiyatlar']=pd.DataFrame({'tarih_saat':actual.index,'PTF (TL/MWh)':actual.to_numpy()})
            ref=maliyet_ve_ozet(actual_firm,actual_firm['referans_plan'],actual_firm['referans_yuklemeler'])[-1]
            ref_cost=float(ref['Karşılaştırılan toplam maliyet (TL)'])
            cases={};case_rows={};applied_costs={s:[] for s in config['forecast_sources']}
            def run_case(key,day,source,planned,previous=None):
                started=time.perf_counter()
                v=copy.deepcopy(actual_firm)
                v['fiyatlar']=pd.DataFrame({'tarih_saat':planned.index,'PTF (TL/MWh)':planned.to_numpy()})
                if previous is not None:
                    # Önceki plan bu karar anının uygun referans devamıdır; ilk referansla karıştırılmaz.
                    v['referans_plan']=previous[0].copy();v['referans_yuklemeler']=previous[1].copy()
                try:
                    result=solve(v,zaman_siniri=config['solver_time_limit_seconds'],goreli_acik=config['mip_relative_gap'],
                                 yerel_iyilestirme=False,fixed_prefix_hours=day*24)
                    real=maliyet_ve_ozet(actual_firm,result[0],result[1])
                    if previous is not None:
                        assert_prefix(previous,result,pd.Timestamp(week)+pd.Timedelta(days=day))
                        boundary=pd.Timestamp(week)+pd.Timedelta(days=day)-pd.Timedelta(hours=1)
                        for r in result[2].loc[result[2]['tarih_saat'].eq(boundary)].itertuples(index=False):
                            boundaries.append(dict(week=week,source=source,decision_day=day,product=r.urun_id,stock_type=r.stok_turu,carried_stock_ton=r.son_stok_ton))
                except (ValueError,AssertionError) as error:
                    failures.append(dict(week=str(week),run_key=key,error_type=type(error).__name__,reason=str(error)))
                    (output/'violations.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2),encoding='utf-8')
                    raise
                status=result[-1]
                wall=time.perf_counter()-started
                row=dict(week=week,run_key=key,decision_day=day,source=source,solver_status=status['durum'],
                    time_limit_reached=bool(status['time_limit_reached']),mip_gap=float(status['goreli_acik']),
                    lower_bound_tl=float(status['alt_sinir_tl']),solver_seconds=float(status['sure_saniye']),wall_seconds=wall,
                    time_limit_seconds=float(config['solver_time_limit_seconds']),actual_cost_tl=float(real[-1]['Karşılaştırılan toplam maliyet (TL)']),
                    expected_cost_tl=float(result[5]['Karşılaştırılan toplam maliyet (TL)']),fixed_prefix_hours=day*24,
                    independent_validation=True,violation_count=0,fixed_columns=int(status['fixed_columns']),
                    initial_reference_warm_start=previous is None,warm_start='initial_reference' if previous is None else 'previous_feasible_continuation',
                    declared_optimal=False,tolerance_optimal=bool(status['tolerans_icinde_optimum']),
                    outside_19_plan_pool=signature(result[0],result[1],week) not in pool)
                row['declared_optimal']=bool(abs(row['actual_cost_tl']-row['lower_bound_tl'])<=config['cost_tolerance_tl']) if source=='oracle' else False
                folder=output/pd.Timestamp(week).strftime('%Y%m%d')/key
                save_run(folder,result,v['fiyatlar'],real[2],row)
                run_rows.append(row);cases[key]=result;case_rows[key]=row
                print(f"{pd.Timestamp(week).date()} {key}: {row['solver_status']}; gap={row['mip_gap']:.4f}",flush=True)
                return result,real
            oracle,_=run_case('oracle',0,'oracle',actual)
            fstart=time.perf_counter();forecasts,_=forecasts_at(prices,week,project,config);forecast_seconds+=time.perf_counter()-fstart
            for source in config['forecast_sources']:
                result,real=run_case(source+'_d0',0,source,planning_prices(actual,0,forecasts[source]))
                applied_costs[source].append(float(real[2].iloc[:24]['karsilastirilan_maliyet_tl'].sum()))
            for day in (1,2):
                updated=None
                if day==1:
                    fstart=time.perf_counter();updated,_=forecasts_at(prices,pd.Timestamp(week)+pd.Timedelta(days=1),project,config);forecast_seconds+=time.perf_counter()-fstart
                for source in config['forecast_sources']:
                    previous=cases[source+f'_d{day-1}']
                    result,real=run_case(source+f'_d{day}',day,source,planning_prices(actual,day,None if updated is None else updated[source]),previous)
                    applied_costs[source].append(float(real[2].iloc[day*24:(day+1)*24]['karsilastirilan_maliyet_tl'].sum()))
            upper=case_rows['oracle']['actual_cost_tl'];lower=case_rows['oracle']['lower_bound_tl']
            policy_costs={'reference':ref_cost,'oracle_incumbent':upper}
            for source in config['forecast_sources']:
                policy_costs[source+'_open']=case_rows[source+'_d0']['actual_cost_tl']
                policy_costs[source+'_rolling']=sum(applied_costs[source])
                if abs(policy_costs[source+'_rolling']-case_rows[source+'_d2']['actual_cost_tl'])>.02:
                    raise AssertionError('Yalnız uygulanan günlerin maliyeti son birleşik planla eşleşmiyor.')
            for policy,cost in policy_costs.items():
                row=dict(week=week,policy=policy,reference_cost_tl=ref_cost,oracle_incumbent_tl=upper,
                         oracle_lower_bound_tl=lower,**decision_metrics(ref_cost,cost,upper,lower,config['cost_tolerance_tl']))
                week_rows.append(row)
            if len([r for r in run_rows if r['week']==week])!=config['milp_runs_per_week']:
                raise AssertionError('Haftalık çözüm sayısı eşit değil.')
            times.append(dict(week=week,wall_seconds=time.perf_counter()-week_start,forecast_seconds=forecast_seconds,
                              solver_seconds=sum(r['solver_seconds'] for r in run_rows if r['week']==week),milp_runs=7))
        run_df=pd.DataFrame(run_rows);week_df=pd.DataFrame(week_rows)
        summary=[]
        for policy,frame in week_df.groupby('policy'):
            capture=aggregate_capture(frame['reference_advantage_tl'].sum(),frame['potential_vs_incumbent_tl'].sum(),frame['potential_upper_tl'].sum())
            summary.append(dict(policy=policy,weeks=4,mean_actual_cost_tl=frame['actual_cost_tl'].mean(),
                mean_oracle_incumbent_gap_tl=frame['oracle_incumbent_gap_tl'].mean(),
                mean_regret_lower_tl=frame['regret_lower_tl'].mean(),mean_regret_upper_tl=frame['regret_upper_tl'].mean(),
                total_savings_tl=frame['reference_advantage_tl'].sum(),**capture))
        summary=pd.DataFrame(summary)
        for name,frame in [('solver_runs',run_df),('weekly_metrics',week_df),('policy_summary',summary),
                           ('runtime_by_week',pd.DataFrame(times)),('rolling_stock_carry',pd.DataFrame(boundaries))]:
            frame.to_csv(output/f'{name}.csv',index=False,encoding='utf-8-sig')
        upload(engine,exp_id,run_rows,week_rows);first=snapshot(engine,exp_id)
        upload(engine,exp_id,run_rows,week_rows);second=snapshot(engine,exp_id)
        if first!=second:raise AssertionError('Görev 4 SQL yüklemesi idempotent değil.')
        parent.verify_lock(project,project/config['hgb_config'],parent_output)
        if any(digest(project/name)!=value for name,value in source_hashes.items()):raise ValueError('Deney kaynağı çalışırken değişti.')
        elapsed=time.perf_counter()-overall_start
        per_week=np.array([t['wall_seconds'] for t in times])
        estimate=dict(pilot_total_seconds=elapsed,pilot_week_seconds=per_week.tolist(),milp_runs=28,
                      estimated_34_weeks_minutes=float((per_week.mean()*34+setup_seconds)/60),
                      observed_week_min_max_scaled_to_34_minutes=[float((per_week.min()*34+setup_seconds)/60),float((per_week.max()*34+setup_seconds)/60)],
                      solver_limits_sum_34_minutes=34*7*config['solver_time_limit_seconds']/60,
                      full_34_executed=False,approval_required_before_full_run=True)
        result=dict(experiment_id=exp_id,runtime=estimate,results_idempotent=True,
                    sql_rows={k:len(v) for k,v in second.items()},all_28_solutions_independently_validated=True,
                    violations=0,oracle_exact_weeks=int(week_df.loc[week_df['policy'].eq('oracle_incumbent'),'oracle_exact_certified'].sum()),
                    outside_pool_runs=int(run_df['outside_19_plan_pool'].sum()),locked_test_evaluated=False,stochastic_mode=False)
        (output/'pilot_info.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (output/'violations.json').write_text('[]\n',encoding='utf-8')
        write_report(result,summary,output,config)
        print(summary.round(4).to_string(index=False),flush=True)
        print(json.dumps(result,ensure_ascii=True),flush=True)
    finally:engine.dispose()


def write_report(info,summary,output,config):
    lines=['# Görev 4 — dört haftalık PostgreSQL MILP pilotu','',
      'Geliştirme fold indeksleri 0, 11, 22, 33 önceden sabitlendi. Kilitli 10 hafta açılmadı. 34 haftalık çalışma başlatılmadı.','',
      'Firma ve fiyat geçmişi kod.db PostgreSQL okuma katmanından alındı. Tahminler bu geçmişten yeniden üretildi; CSV tahmin veya aday plan havuzu optimizasyon girdisi değildir. 19 plan arşivi yalnız çıktı yeniliğini denetlemek için kullanıldı.','',
      'Her haftada aynı ayarlarla 7 MILP: bir gerçek-fiyat oracle, iki ilk karar ve her yöntem için iki günlük yeniden çözüm. HGB/ensemble açık döngü ve rolling ilk çözümü aynıdır; ekstra koşumların en iyisi seçilmedi. Başlangıç referansı ilk çözümlere warm starttır; ertesi gün geçmişe uygun son plan devamı warm start olur.','',
      f"Her MILP: {config['solver_time_limit_seconds']} saniye, gap hedefi {config['mip_relative_gap']}, seed 42, tek thread, yerel ön arama kapalı. Süre sınırı solver.run içindir; kurulum/tahmin/doğrulama ayrıca ölçülür.",'',
      'Rolling ufuk, aynı üç günlük sipariş için 72→48→24 saattir. Geçmiş tam modelde sabitlenir; stok, ürün ayarı, minimum süre ve iş emri ilerlemesi sıfırlanmaz. Yalnız o günün 24 saati uygulanır; uygulanan günlük maliyetlerin toplamı birleşik son planın gerçek maliyetiyle karşılaştırılır.','',
      'Oracle tam MILP uzayında gerçek fiyatlarla çözülür; süre/gap nedeniyle bulunan plan kesin optimum değildir. C* ∈ [oracle alt sınırı, oracle uygun plan maliyeti]. Bu yüzden gerçek regret için alt/üst aralıklar, kesin sertifika varsa exact_regret; ayrıca oracle bulunan planına göre ham fark ayrı tutulur. Negatif ham fark, gerçek negatif regret diye sunulmaz. Tahminli/rolling amaçlarının alt sınırları oracle sınırı yerine kullanılmaz.','',
      'Bilgi yakalama oranı toplam kazanç / toplam oracle potansiyelidir; haftalık oran ortalaması değildir. Oracle optimumu kesin değilse bu oran da bulunan oracle plana göre geçicidir; gerçek oran sınırları ayrıca verilir. Payda sıfırsa tanımsızdır.','',
      '| Politika | Ortalama gerçek maliyet TL | Oracle plana fark TL | Gerçek regret alt–üst TL | Toplam bilgi yakalama (geçici) |','|---|---:|---:|---|---:|']
    for _,r in summary.iterrows():
        capture='tanımsız' if pd.isna(r['capture_vs_incumbent']) else f"{r['capture_vs_incumbent']:.4f}"
        lines.append(f"| {r['policy']} | {r['mean_actual_cost_tl']:.2f} | {r['mean_oracle_incumbent_gap_tl']:.2f} | {r['mean_regret_lower_tl']:.2f}–{r['mean_regret_upper_tl']:.2f} | {capture} |")
    lines+=['',f"28 çözüm bağımsız kontrol edildi. İhlal: {info['violations']}. Oracle kesin sertifikalı hafta: {info['oracle_exact_weeks']}/4. Eski 19 planın dışında çıktı: {info['outside_pool_runs']} koşum. SQL satırları: {info['sql_rows']}; çift yüklemede içerik ve sayılar aynı.",'',
      '## Süre ve onay noktası','',
      f"Pilot toplamı: {info['runtime']['pilot_total_seconds']/60:.2f} dakika. 34 haftanın gözlenen hafta ortalamasından tahmini: {info['runtime']['estimated_34_weeks_minutes']:.2f} dakika. Gözlenen en kısa/uzun haftanın ölçeklenmesi: {info['runtime']['observed_week_min_max_scaled_to_34_minutes']} dakika; bu bir istatistiksel güven aralığı değildir.",
      '34 hafta kullanıcı onayı bekler. Pilot sonuçları diğer bütçeli koşumlarla birleştirilmez.','',
      '## Stokastik mod önerisi','',
      'Bu aşamada uygulanmadı. Önceki senaryoların nominal %80 aralığı yalnız %61,89 kapsama verdiği için risk modeli güvenilir biçimde kalibre edilmiş değildir. Tek ortak çizelgede doğrusal elektrik maliyetinin senaryolar üzerindeki beklentisini minimize etmek, senaryoların ortalama fiyatıyla deterministik çözümle aynıdır; yalnız senaryo sayısını artırmak ek karar değeri sağlamaz. Gerçek ek değer için iyi kalibre edilmiş senaryolar ve açıkça tanımlı recourse/nonanticipativity veya risk hedefi gerekir. Mevcut pilot böyle bir değer iddiası taşımaz.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    args=parser.parse_args()
    pilot(args.project.resolve(),args.output.resolve(),args.config.resolve())
