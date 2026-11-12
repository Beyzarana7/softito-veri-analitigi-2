"""Ayrı 60 saniyelik dört hafta / üç tahmin yöntemi MILP pilotu."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

from common import digest,shift_firm,signature,assert_prefix,save_run
from forecasting import forecasts_at,planning_prices,load_module
from metrics import decision_metrics,aggregate_capture
from costs import cost_breakdown,ADDITIVE


def write_json(path,value):
    path.write_text(json.dumps(value,default=str,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def tree_hashes(project,paths):
    return {str(p.relative_to(project)):digest(p) for folder in paths for p in sorted(folder.rglob('*')) if p.is_file()}


def planned_runs(weeks,sources):
    return [dict(week=str(w),run_key=key,source=source,decision_day=day)
            for w in weeks for key,source,day in [('oracle','oracle',0)]+[(f'{s}_d{d}',s,d) for d in (0,1,2) for s in sources]]


def pilot(project,output,config_file):
    start=time.perf_counter()
    if output.exists():raise FileExistsError('Ayrı deney için çıktı klasörü mevcut olmamalı.')
    sys.path.insert(0,str(project));sys.path.insert(0,str(project/'src'))
    from kod.db import create_db_engine,read_firm,read_prices
    from firma_cizelgeleme import maliyet_ve_ozet
    from solver import solve
    from storage import upload,snapshot
    config=json.loads(config_file.read_text(encoding='utf-8'))
    old_output=project/config['previous_pilot']
    old_manifest=json.loads((old_output/'manifest.json').read_text(encoding='utf-8'))
    old_config=json.loads((old_output/'config_snapshot.json').read_text(encoding='utf-8'))
    for key,value in old_config.items():
        if key not in {'solver_time_limit_seconds','forecast_sources','milp_runs_per_week'} and config[key]!=value:
            raise ValueError(f'Korunması gereken ayar değişmiş: {key}')
    if config['solver_time_limit_seconds']!=60 or config['forecast_sources']!=['hgb','ensemble','naive'] or config['milp_runs_per_week']!=10:
        raise ValueError('Onay yalnız 60 saniye, üç yöntem ve haftada 10 MILP içindir.')
    if config['plan_change_cost_tl_per_resource_hour']!=0:raise ValueError('Mevcut sıfır değişiklik gideri korunmalı.')
    if config['sensitivity_proposal']['executed']:raise ValueError('Duyarlılık deneyi onaylanmadı.')
    preserved=tree_hashes(project,[old_output,project/config['previous_module']])
    parent=load_module(project/'experiments/02_walk_forward/protocol.py','protocol60')
    folds,_=parent.verify_lock(project,project/config['hgb_config'],project/config['parent_protocol'])
    dev=folds.loc[folds['split'].eq('development')].reset_index(drop=True)
    weeks=dev.iloc[config['pilot_fold_indices']]['decision_origin'].tolist()
    locked_start=folds.loc[folds['split'].eq('locked_test'),'decision_origin'].min()
    if [str(w) for w in weeks]!=old_manifest['weeks']:raise ValueError('Pilot haftaları farklı.')
    schedule=planned_runs(weeks,config['forecast_sources'])
    if len(schedule)!=40 or len({(r['week'],r['run_key']) for r in schedule})!=40:raise ValueError('40 benzersiz koşum gerekli.')
    engine=create_db_engine(project)
    try:
        firm=read_firm(engine);prices=read_prices(engine)
        prices=prices.loc[prices.index<locked_start].copy()
        inputs={k:hashlib.sha256(v.to_csv(index=False).encode()).hexdigest() for k,v in firm.items()}
        inputs['postgresql_price_history']=hashlib.sha256(prices.to_csv().encode()).hexdigest()
        if inputs!=old_manifest['input_hashes']:raise ValueError('PostgreSQL girdileri 15 saniyelik deneyden farklı.')
        sources=list(Path(__file__).parent.glob('*.py'))+[config_file,project/config['hgb_config'],project/config['ensemble_config']]
        source_hashes={str(p.relative_to(project)):digest(p) for p in sources}
        exp_id='pilot04_60s_'+hashlib.sha256(json.dumps([config,inputs,source_hashes],sort_keys=True).encode()).hexdigest()[:16]
        old_sql=snapshot(engine,old_manifest['experiment_id'])
        output.mkdir(parents=True)
        (output/'config_snapshot.json').write_bytes(config_file.read_bytes())
        pd.DataFrame(schedule).to_csv(output/'planned_runs.csv',index=False,encoding='utf-8-sig')
        proposal=config['sensitivity_proposal'].copy()
        proposal['weeks']=[str(w) for w in dev.iloc[proposal['fold_indices']]['decision_origin']]
        proposal.update(locked_test_evaluated=False,outcome_based_selection=False,executed=False,
                        protocols=['oracle','hgb_open','ensemble_open','naive_open'],milp_runs=3*5*4,
                        note='Only initial decisions; no rolling. 60 solves, maximum solver limits sum 60 minutes; not executed.')
        write_json(output/'sensitivity_proposal.json',proposal)
        write_json(output/'manifest.json',dict(experiment_id=exp_id,weeks=[str(w) for w in weeks],config=config,
                   input_hashes=inputs,source_hashes=source_hashes,preserved_files=preserved,
                   inputs='PostgreSQL via kod.db',previous_plans_used_as_warm_start=False,
                   locked_test_evaluated=False,stochastic_mode=False,full_34_executed=False))
        runs=[];weekly=[];timing=[];boundaries=[];components=[]
        setup=time.perf_counter()-start
        for week in weeks:
            week_start=time.perf_counter();forecast_seconds=0.
            actual=prices.reindex(pd.date_range(week,periods=72,freq='h'))
            if actual.isna().any() or actual.index.max()>=locked_start:raise ValueError('Eksik veya kilitli fiyat.')
            v_actual=shift_firm(firm,week)
            v_actual['fiyatlar']=pd.DataFrame({'tarih_saat':actual.index,'PTF (TL/MWh)':actual.to_numpy()})
            reference=maliyet_ve_ozet(v_actual,v_actual['referans_plan'],v_actual['referans_yuklemeler'])
            ref_cost=float(reference[-1]['Karşılaştırılan toplam maliyet (TL)'])
            ref_components=cost_breakdown(v_actual,reference)
            cases={};rows={};applied={s:[] for s in config['forecast_sources']}
            def run_case(key,day,source,planned,previous=None):
                tick=time.perf_counter();v=copy.deepcopy(v_actual)
                v['fiyatlar']=pd.DataFrame({'tarih_saat':planned.index,'PTF (TL/MWh)':planned.to_numpy()})
                if previous is not None:
                    v['referans_plan']=previous[0].copy();v['referans_yuklemeler']=previous[1].copy()
                try:
                    result=solve(v,zaman_siniri=60,goreli_acik=config['mip_relative_gap'],yerel_iyilestirme=False,
                                 fixed_prefix_hours=day*24,solver_seed=config['seed'])
                    real=maliyet_ve_ozet(v_actual,result[0],result[1])
                    costs=cost_breakdown(v_actual,real)
                    if previous is not None:
                        assert_prefix(previous,result,week+pd.Timedelta(days=day))
                        boundary=week+pd.Timedelta(days=day)-pd.Timedelta(hours=1)
                        for r in result[2].loc[result[2]['tarih_saat'].eq(boundary)].itertuples(index=False):
                            boundaries.append(dict(week=week,source=source,decision_day=day,product=r.urun_id,stock_type=r.stok_turu,carried_stock_ton=r.son_stok_ton))
                except (ValueError,AssertionError) as error:
                    write_json(output/'violations.json',[dict(week=str(week),run_key=key,error_type=type(error).__name__,reason=str(error))]);raise
                status=result[-1]
                row=dict(week=week,run_key=key,source=source,decision_day=day,solver_status=status['durum'],
                    solver_objective_tl=status['solver_objective_tl'],expected_cost_tl=float(result[5]['Karşılaştırılan toplam maliyet (TL)']),
                    actual_cost_tl=float(real[-1]['Karşılaştırılan toplam maliyet (TL)']),lower_bound_tl=float(status['alt_sinir_tl']),
                    mip_gap=float(status['goreli_acik']),solver_seconds=float(status['sure_saniye']),wall_seconds=time.perf_counter()-tick,
                    time_limit_reached=bool(status['time_limit_reached']),time_limit_seconds=60.,fixed_prefix_hours=day*24,
                    fixed_columns=int(status['fixed_columns']),independent_validation=True,violation_count=0,
                    requested_seed=status['requested_seed'],effective_seed=status['effective_seed'],seed_option_accepted=status['seed_option_accepted'],
                    solver_version=status['solver_version'],mip_node_count=int(status['mip_node_count']),
                    warm_start='initial_postgresql_reference' if previous is None else 'own_previous_day_continuation',
                    warm_start_signature=signature(v['referans_plan'],v['referans_yuklemeler'],week),
                    warm_start_cost_tl=float(status['baslangic_maliyet_tl']),plan_signature=signature(result[0],result[1],week),
                    tolerance_optimal=bool(status['tolerans_icinde_optimum']),declared_optimal=False)
                row.update({name:float(costs[name].sum()) for name in ADDITIVE+['total_electricity_tl']})
                folder=output/week.strftime('%Y%m%d')/key
                save_run(folder,result,v['fiyatlar'],real[2],row)
                costs.to_csv(folder/'cost_components_hourly.csv',index=False,encoding='utf-8-sig')
                runs.append(row);rows[key]=row;cases[key]=result
                print(f"{week.date()} {key}: {row['solver_status']}; actual={row['actual_cost_tl']:.2f}; gap={row['mip_gap']:.5f}; seed={row['effective_seed']}",flush=True)
                return costs
            run_case('oracle',0,'oracle',actual)
            for day in (0,1,2):
                forecasts=None
                if day<2:
                    tick=time.perf_counter();forecasts,audit=forecasts_at(prices,week+pd.Timedelta(days=day),project,config)
                    forecast_seconds+=time.perf_counter()-tick
                    write_json(output/week.strftime('%Y%m%d')/f'forecast_audit_d{day}.json',audit)
                for source in config['forecast_sources']:
                    previous=None if day==0 else cases[f'{source}_d{day-1}']
                    costs=run_case(f'{source}_d{day}',day,source,planning_prices(actual,day,None if forecasts is None else forecasts[source]),previous)
                    applied[source].append(costs.iloc[day*24:(day+1)*24].copy())
            upper=rows['oracle']['actual_cost_tl'];lower=rows['oracle']['lower_bound_tl']
            policies={'reference':(ref_cost,ref_components),'oracle_incumbent':(upper,None)}
            for source in config['forecast_sources']:
                policies[source+'_open']=(rows[source+'_d0']['actual_cost_tl'],None)
                merged=pd.concat(applied[source],ignore_index=True)
                rolling=float(merged['total_cost_tl'].sum())
                if abs(rolling-rows[source+'_d2']['actual_cost_tl'])>.02:raise AssertionError('Uygulanan günlük maliyet birleşik planla eşleşmiyor.')
                merged.to_csv(output/week.strftime('%Y%m%d')/f'{source}_executed_costs.csv',index=False,encoding='utf-8-sig')
                policies[source+'_rolling']=(rolling,merged)
            for policy,(cost,costs) in policies.items():
                if cost<lower-.02:raise AssertionError('Uygun plan oracle alt sınırından ucuz; sınır kontrol edilmeli.')
                row=dict(week=week,policy=policy,reference_cost_tl=ref_cost,oracle_incumbent_tl=upper,
                         oracle_lower_bound_tl=lower,**decision_metrics(ref_cost,cost,upper,lower))
                weekly.append(row)
                source_row=rows['oracle'] if policy=='oracle_incumbent' else rows.get(policy.replace('_open','_d0'))
                values={k:float(costs[k].sum()) for k in ADDITIVE+['total_electricity_tl']} if costs is not None else {k:source_row[k] for k in ADDITIVE+['total_electricity_tl']}
                components.append(dict(week=week,policy=policy,total_cost_tl=cost,**values))
            if len([r for r in runs if r['week']==week])!=10:raise AssertionError('Haftalık 10 koşum sağlanmadı.')
            timing.append(dict(week=week,wall_seconds=time.perf_counter()-week_start,forecast_seconds=forecast_seconds,
                               solver_seconds=sum(r['solver_seconds'] for r in runs if r['week']==week),milp_runs=10))
        run_df=pd.DataFrame(runs);week_df=pd.DataFrame(weekly);summary=[]
        for policy,f in week_df.groupby('policy'):
            summary.append(dict(policy=policy,weeks=4,mean_actual_cost_tl=float(f['actual_cost_tl'].mean()),
                total_savings_tl=float(f['reference_advantage_tl'].sum()),mean_oracle_incumbent_gap_tl=float(f['oracle_incumbent_gap_tl'].mean()),
                mean_regret_lower_tl=float(f['regret_lower_tl'].mean()),mean_regret_upper_tl=float(f['regret_upper_tl'].mean()),
                **aggregate_capture(float(f['reference_advantage_tl'].sum()),float(f['potential_vs_incumbent_tl'].sum()),float(f['potential_upper_tl'].sum()))))
        actual_runs=[(str(r['week']),r['run_key']) for r in runs]
        if actual_runs!=[(r['week'],r['run_key']) for r in schedule]:raise AssertionError('Koşum sırası/liste farklı.')
        for name,frame in [('solver_runs',run_df),('weekly_metrics',week_df),('policy_summary',pd.DataFrame(summary)),
                           ('runtime_by_week',pd.DataFrame(timing)),('rolling_stock_carry',pd.DataFrame(boundaries)),('policy_cost_components',pd.DataFrame(components))]:
            frame.to_csv(output/f'{name}.csv',index=False,encoding='utf-8-sig')
        upload(engine,exp_id,runs,weekly);first=snapshot(engine,exp_id)
        upload(engine,exp_id,runs,weekly)
        if first!=snapshot(engine,exp_id):raise AssertionError('SQL idempotans kontrolü başarısız.')
        if old_sql!=snapshot(engine,old_manifest['experiment_id']):raise AssertionError('Eski deney SQL sonuçları değişti.')
        parent.verify_lock(project,project/config['hgb_config'],project/config['parent_protocol'])
        if tree_hashes(project,[old_output,project/config['previous_module']])!=preserved:raise AssertionError('Önceki deney dosyaları değişti.')
        if any(digest(project/k)!=h for k,h in source_hashes.items()):raise AssertionError('Kaynak çalışırken değişti.')
        elapsed=time.perf_counter()-start;seconds=np.array([t['wall_seconds'] for t in timing])
        info=dict(experiment_id=exp_id,previous_experiment_id=old_manifest['experiment_id'],milp_runs=40,
             total_pilot_seconds=elapsed,estimated_34_weeks_minutes=float((seconds.mean()*34+setup)/60),
             observed_min_max_scaled_to_34_minutes=[float((seconds.min()*34+setup)/60),float((seconds.max()*34+setup)/60)],
             maximum_solver_limits_34_minutes=340,all_solutions_validated=True,violation_count=0,sql_idempotent=True,
             sql_rows={k:len(v) for k,v in first.items()},locked_test_evaluated=False,full_34_executed=False,
             sensitivity_executed=False,task5_executed=False,previous_files_and_sql_preserved=True,
             exact_oracle_weeks=int(week_df.loc[week_df['policy'].eq('oracle_incumbent'),'oracle_exact_certified'].sum()))
        write_json(output/'pilot_info.json',info);write_json(output/'violations.json',[])
        print(json.dumps(info,ensure_ascii=True),flush=True)
        print(pd.DataFrame(summary).round(4).to_string(index=False),flush=True)
    finally:engine.dispose()


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    args=parser.parse_args();pilot(args.project.resolve(),args.output.resolve(),args.config.resolve())
