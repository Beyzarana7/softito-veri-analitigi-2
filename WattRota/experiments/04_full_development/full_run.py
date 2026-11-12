"""34 geliştirme haftası; sabit 60 saniye / seed 42; tek deneme ve haftalık checkpoint."""
import argparse
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

PROJECT=Path(__file__).resolve().parents[2]
sys.path.extend([str(PROJECT),str(PROJECT/'src'),str(PROJECT/'experiments/04_direct_milp_60s'),str(PROJECT/'experiments/04_incumbent_audit')])
from common import shift_firm,signature,assert_prefix
from forecasting import forecasts_at,planning_prices,load_module
from costs import cost_breakdown,ADDITIVE
from metrics import decision_metrics,aggregate_capture
from instrumentation import Recorder
from instrumented_solver import solve
from model_audit import load_builder,evaluate,assert_same_model,tightened_regret


def write_json(path,value):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,default=str,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temporary.replace(path)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def tree_hashes(project,folders):return {str(p.relative_to(project)):digest(p) for f in folders for p in sorted(f.rglob('*')) if p.is_file()}
def records(frame):return [{k:(None if pd.isna(v) else v) for k,v in r.items()} for r in frame.to_dict('records')]


def process_active(pid):
    if sys.platform!='win32':raise RuntimeError('Bu çalıştırıcının süreç kilidi Windows içindir.')
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle:
        if ctypes.get_last_error()==87:return False
        raise RuntimeError('Önceki sürecin durumu doğrulanamadı; ikinci süreç başlatılmadı.')
    try:
        code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(wintypes.HANDLE(handle),ctypes.byref(code)):raise RuntimeError('Süreç durumu okunamadı.')
        return code.value==259
    finally:kernel.CloseHandle(wintypes.HANDLE(handle))


@contextlib.contextmanager
def keep_awake():
    requested=False
    if sys.platform=='win32':requested=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
    try:yield requested
    finally:
        if requested:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def add_posthoc(week,firm,plans,costs,oracle_row,builder,folder):
    from firma_cizelgeleme import maliyet_ve_ozet
    reference=builder(firm,zaman_siniri=1,yerel_iyilestirme=False)
    audits=[];eligible=[];violations=[]
    for policy,(plan,loads) in plans.items():
        try:
            actual=maliyet_ve_ozet(firm,plan,loads)
            model=builder(firm,zaman_siniri=1,yerel_iyilestirme=False,baslangic_cozumu=(plan,loads))
            assert_same_model(reference,model)
            result=evaluate(model,float(actual[-1]['Karşılaştırılan toplam maliyet (TL)']))
            if abs(result['independent_cost_tl']-costs[policy])>.02:raise ValueError('Birleşik rolling maliyeti uyuşmuyor.')
            audits.append(dict(week=week,policy=policy,**{k:v for k,v in result.items() if k!='violations'}))
            for v in result['violations']:violations.append(dict(week=str(week),policy=policy,**v))
            if result['full_model_feasible']:eligible.append((policy,costs[policy]))
        except Exception as error:
            audits.append(dict(week=week,policy=policy,full_model_feasible=False))
            violations.append(dict(week=str(week),policy=policy,error_type=type(error).__name__,reason=str(error)))
    pd.DataFrame(audits).to_csv(folder/'full_model_audit.csv',index=False,encoding='utf-8-sig')
    write_json(folder/'audit_violations.json',violations)
    if not eligible:return audits,[],[],violations
    upper=min(c for _,c in eligible)
    best=dict(week=week,verified_best_known_feasible_cost_tl=upper,
              winning_policies=';'.join(p for p,c in eligible if abs(c-upper)<=.02),posthoc=True,
              original_oracle_upper_tl=None if oracle_row is None else oracle_row['actual_cost_tl'],
              oracle_lower_bound_tl=None if oracle_row is None else oracle_row['lower_bound_tl'])
    tighter=[]
    if oracle_row is not None:
        for policy,cost in eligible:
            low,high=tightened_regret(cost,oracle_row['lower_bound_tl'],upper)
            tighter.append(dict(week=week,policy=policy,actual_cost_tl=cost,
                   posthoc_verified_upper_tl=upper,oracle_lower_bound_tl=oracle_row['lower_bound_tl'],
                   tightened_regret_lower_tl=low,tightened_regret_upper_tl=high,
                   posthoc=True,independent_information_capture=None))
    return audits,[best],tighter,violations


def week_run(project,output,week,base_firm,prices,config,builder):
    from firma_cizelgeleme import maliyet_ve_ozet
    folder=output/week.strftime('%Y%m%d');folder.mkdir(exist_ok=True)
    actual=prices.reindex(pd.date_range(week,periods=72,freq='h'))
    if actual.isna().any():raise ValueError('Hafta fiyatları eksik.')
    firm=shift_firm(base_firm,week)
    firm['fiyatlar']=pd.DataFrame({'tarih_saat':actual.index,'PTF (TL/MWh)':actual.to_numpy()})
    reference=maliyet_ve_ozet(firm,firm['referans_plan'],firm['referans_yuklemeler'])
    ref_cost=float(reference[-1]['Karşılaştırılan toplam maliyet (TL)'])
    cases={};success=[];attempts=[];applied={s:[] for s in config['forecast_sources']}
    executed={s:([],[]) for s in config['forecast_sources']}
    tick=time.perf_counter()
    def register(key,source,day,result,parts,row):
        success.append(row);cases[key]=result
        if source!='oracle':
            lo=week+pd.Timedelta(days=day);hi=lo+pd.Timedelta(days=1)
            applied[source].append(parts.iloc[day*24:(day+1)*24].copy())
            executed[source][0].append(result[0].loc[result[0].tarih_saat.ge(lo)&result[0].tarih_saat.lt(hi)].copy())
            executed[source][1].append(result[1].loc[result[1].tarih_saat.ge(lo)&result[1].tarih_saat.lt(hi)].copy())
    def case(key,source,day,planned,previous=None,blocked_reason=None):
        attempt=dict(week=week,run_key=key,source=source,decision_day=day,attempt=1)
        run_folder=folder/key;run_folder.mkdir(exist_ok=True)
        if (run_folder/'run.json').exists():
            row=json.loads((run_folder/'run.json').read_text(encoding='utf-8'));row['week']=week
            p=pd.read_csv(run_folder/'plan.csv',keep_default_na=False,parse_dates=['tarih_saat'])
            y=pd.read_csv(run_folder/'loads.csv',parse_dates=['tarih_saat'])
            validation=maliyet_ve_ozet(firm,p,y);parts=cost_breakdown(firm,validation)
            if abs(float(validation[-1]['Karşılaştırılan toplam maliyet (TL)'])-row['actual_cost_tl'])>.02:raise ValueError('Kayıtlı çözüm yeniden doğrulanamadı.')
            result=(p,y,validation[0],validation[1],validation[2],validation[3],row)
            if previous is not None:assert_prefix(previous,result,week+pd.Timedelta(days=day))
            register(key,source,day,result,parts,row)
            attempt.update(state='success',recovered=True,solver_status=row['solver_status'],actual_cost_tl=row['actual_cost_tl'])
            attempts.append(attempt);write_json(run_folder/'attempt.json',attempt)
            print(f'RESTORED {week.date()} {key}; no solve repeated',flush=True);return
        if (run_folder/'attempt.json').exists():
            old=json.loads((run_folder/'attempt.json').read_text(encoding='utf-8'))
            if old['state']=='running':
                old.update(state='interrupted',reason='Previous process ended before a verified solution was saved; not automatically retried.')
                write_json(run_folder/'attempt.json',old)
            attempts.append(old);return
        rec=Recorder(run_folder);result=None
        if blocked_reason is not None:
            attempt.update(state='blocked',reason=blocked_reason)
            attempts.append(attempt);write_json(run_folder/'attempt.json',attempt);return
        started=time.perf_counter()
        write_json(run_folder/'attempt.json',dict(attempt,state='running',pid=os.getpid()))
        try:
            v={k:f.copy(deep=True) for k,f in firm.items()}
            v['fiyatlar']=pd.DataFrame({'tarih_saat':planned.index,'PTF (TL/MWh)':planned.to_numpy()})
            if previous is not None:v['referans_plan']=previous[0].copy();v['referans_yuklemeler']=previous[1].copy()
            result=solve(v,zaman_siniri=60,goreli_acik=.001,yerel_iyilestirme=False,fixed_prefix_hours=24*day,
                         solver_seed=42,log_dosyasi=run_folder/'solver_trace.txt',recorder=rec)
            validation=maliyet_ve_ozet(firm,result[0],result[1]);parts=cost_breakdown(firm,validation)
            if previous is not None:assert_prefix(previous,result,week+pd.Timedelta(days=day))
            rec.finish()
            diagnostics=rec.summary()
            if rec.errors:raise ValueError('Callback kaydı hatalı: '+str(rec.errors))
            for stage in ('before_model','after_model','before_run','after_run'):
                if diagnostics['options'][stage]['random_seed']['value']!=42 or diagnostics['options'][stage]['threads']['value']!=1:
                    raise ValueError('Çözücü seed/thread ayarı korunmadı.')
            info=result[-1]
            row=dict(week=week,run_key=key,source=source,decision_day=day,
                solver_status=info['durum'],solver_objective_tl=info['solver_objective_tl'],expected_cost_tl=float(result[5]['Karşılaştırılan toplam maliyet (TL)']),
                actual_cost_tl=float(validation[-1]['Karşılaştırılan toplam maliyet (TL)']),lower_bound_tl=float(info['alt_sinir_tl']),mip_gap=float(info['goreli_acik']),
                solver_seconds=float(info['sure_saniye']),wall_seconds=time.perf_counter()-started,time_limit_seconds=60.,
                time_limit_reached=bool(info['time_limit_reached']),fixed_prefix_hours=24*day,fixed_columns=int(info['fixed_columns']),
                independent_validation=True,violation_count=0,mip_node_count=int(info['mip_node_count']),solver_version=info['solver_version'],
                requested_seed=42,effective_seed=int(info['effective_seed']),warm_start_api_status=diagnostics['api_status'].get('setSolution'),
                native_mip_start_feasible_message=diagnostics['native_mip_start_feasible_message'],
                mip_solution_callback_events=rec.counts['mip_solution'],improving_solution_callback_events=rec.counts['mip_improving_solution'],
                warm_start='initial_postgresql_reference' if day==0 else 'own_previous_day_continuation',
                warm_start_signature=signature(v['referans_plan'],v['referans_yuklemeler'],week),
                plan_signature=signature(result[0],result[1],week),declared_optimal=False,
                tolerance_optimal=bool(info['tolerans_icinde_optimum']),solver_diagnostics=diagnostics)
            row.update({k:float(parts[k].sum()) for k in ADDITIVE+['total_electricity_tl']})
            for name,f in [('plan',result[0]),('loads',result[1]),('stocks',result[2]),('planning_prices',v['fiyatlar']),
                           ('actual_hourly_cost',validation[2]),('cost_components_hourly',parts)]:
                f.to_csv(run_folder/f'{name}.csv',index=False,encoding='utf-8-sig')
            write_json(run_folder/'run.json',row)
            register(key,source,day,result,parts,row)
            attempt.update(state='success',solver_status=row['solver_status'],actual_cost_tl=row['actual_cost_tl'])
        except Exception as error:
            attempt.update(state='failed',error_type=type(error).__name__,reason=str(error))
        finally:
            rec.finish();attempt['wall_seconds']=time.perf_counter()-started
            attempts.append(attempt);write_json(run_folder/'attempt.json',attempt)
            print(f"RUN {week.date()} {key} {attempt['state']} elapsed={attempt['wall_seconds']:.1f}s",flush=True)
    case('oracle','oracle',0,actual)
    for day in (0,1,2):
        forecasts=None;forecast_error=None
        if day<2:
            try:
                forecasts,audit=forecasts_at(prices,week+pd.Timedelta(days=day),project,config)
                write_json(folder/f'forecast_audit_d{day}.json',audit)
            except Exception as error:
                forecast_error=type(error).__name__+': '+str(error);write_json(folder/f'forecast_failure_d{day}.json',dict(reason=forecast_error))
        for source in config['forecast_sources']:
            previous=None if day==0 else cases.get(f'{source}_d{day-1}')
            reason=forecast_error or ('Previous decision failed; no policy continuation.' if day>0 and previous is None else None)
            planned=None if reason else planning_prices(actual,day,None if forecasts is None else forecasts[source])
            case(f'{source}_d{day}',source,day,planned,previous,reason)
    rows_by_key={r['run_key']:r for r in success};oracle=rows_by_key.get('oracle')
    plans={'reference':(firm['referans_plan'],firm['referans_yuklemeler'])};costs={'reference':ref_cost}
    reference_parts=cost_breakdown(firm,reference)
    components=[dict(week=week,policy='reference',**{k:float(reference_parts[k].sum()) for k in ADDITIVE+['total_electricity_tl','total_cost_tl']})]
    for source in ['oracle']+config['forecast_sources']:
        key='oracle' if source=='oracle' else source+'_d0';r=rows_by_key.get(key)
        if r is not None:
            policy='oracle_incumbent' if source=='oracle' else source+'_open'
            plans[policy]=(cases[key][0],cases[key][1]);costs[policy]=r['actual_cost_tl']
            components.append(dict(week=week,policy=policy,total_cost_tl=r['actual_cost_tl'],**{k:r[k] for k in ADDITIVE+['total_electricity_tl']}))
        if source!='oracle' and len(applied[source])==3:
            policy=source+'_rolling';parts=pd.concat(applied[source],ignore_index=True)
            plans[policy]=(pd.concat(executed[source][0],ignore_index=True),pd.concat(executed[source][1],ignore_index=True))
            costs[policy]=float(parts.total_cost_tl.sum())
            if abs(costs[policy]-rows_by_key[source+'_d2']['actual_cost_tl'])>.02:raise AssertionError('Rolling birleşim maliyeti farklı.')
            plans[policy][0].to_csv(folder/f'{policy}_executed_plan.csv',index=False,encoding='utf-8-sig')
            plans[policy][1].to_csv(folder/f'{policy}_executed_loads.csv',index=False,encoding='utf-8-sig')
            components.append(dict(week=week,policy=policy,**{k:float(parts[k].sum()) for k in ADDITIVE+['total_electricity_tl','total_cost_tl']}))
    audits,best,tighter,violations=add_posthoc(week,firm,plans,costs,oracle,builder,folder)
    eligible={a['policy'] for a in audits if a['full_model_feasible']}
    metrics=[]
    for policy,cost in costs.items():
        if policy not in eligible:continue
        if oracle is not None:
            metrics.append(dict(week=week,policy=policy,reference_cost_tl=ref_cost,oracle_incumbent_tl=oracle['actual_cost_tl'],
                oracle_lower_bound_tl=oracle['lower_bound_tl'],**decision_metrics(ref_cost,cost,oracle['actual_cost_tl'],oracle['lower_bound_tl'])))
    result=dict(success=success,attempts=attempts,metrics=metrics,components=components,audits=audits,best=best,tighter=tighter)
    write_json(folder/'week_checkpoint.json',result)
    state=dict(week=week,successful_solves=len(success),failed_solves=sum(a['state']=='failed' for a in attempts),
               blocked_solves=sum(a['state']=='blocked' for a in attempts),violations=len(violations),wall_seconds=time.perf_counter()-tick,
               complete=len(success)==10 and len(eligible)==8 and not violations)
    write_json(folder/'week_status.json',state)
    return result,state


def main(project,output,config_path,resume=False):
    from kod.db import create_db_engine,read_firm,read_prices
    from storage import upload,snapshot
    from persistence import persist_aux
    existing=output.exists()
    if existing and not resume:raise FileExistsError('Çıktı mevcut; yeni süreç başlatılmadı. Yalnız açık resume-pending kullanılabilir.')
    if existing:
        if (output/'completion.json').exists() and json.loads((output/'completion.json').read_text(encoding='utf-8')).get('stage')=='complete':raise ValueError('Çalışma tamamlanmış; tekrar başlatılmaz.')
        lock=json.loads((output/'process.json').read_text(encoding='utf-8'))
        if process_active(lock['pid']):raise ValueError('Önceki süreç halen çalışıyor; ikinci süreç başlatılmaz.')
    config=json.loads(config_path.read_text(encoding='utf-8'))
    if config['phase']!='approved_full_development' or config['seed']!=42 or config['solver_time_limit_seconds']!=60 or config['solver_threads']!=1 or config['mip_relative_gap']!=.001 or config['local_search']:
        raise ValueError('Onaylanan sabit ayarlar gerekli.')
    if any(config[k] for k in ['locked_test_allowed','stochastic_mode','seed_experiment','task5','automatic_solver_retry']):raise ValueError('Kapsam dışı çalışma yasak.')
    if config['forecast_sources']!=['hgb','ensemble','naive'] or config['milp_runs_per_week']!=10:raise ValueError('Üç yöntem / 10 koşum gerekli.')
    parent=load_module(project/'experiments/02_walk_forward/protocol.py','full34_protocol')
    folds,_=parent.verify_lock(project,project/config['hgb_config'],project/config['parent_protocol'])
    dev=folds.loc[folds['split'].eq('development')];weeks=dev.decision_origin.tolist()
    if len(weeks)!=34 or not dev.target_end.lt(folds.loc[folds.split.eq('locked_test'),'decision_origin'].min()).all():raise ValueError('34 geliştirme haftası ve kilit sınırı gerekli.')
    pilot=project/config['pilot'];pilot_manifest=json.loads((pilot/'manifest.json').read_text(encoding='utf-8'))
    preserved=tree_hashes(project,[pilot,project/'data/results/direct_milp_04_pilot',project/'data/results/direct_milp_04_incumbent_audit'])
    source_paths=list(Path(__file__).parent.glob('*.py'))+[config_path]+list((project/'experiments/04_direct_milp_60s').glob('*.py'))+list((project/'experiments/04_incumbent_audit').glob('*.py'))+[project/config['hgb_config'],project/config['ensemble_config'],project/'src/firma_cizelgeleme.py']
    sources={str(p.relative_to(project)):digest(p) for p in source_paths}
    engine=create_db_engine(project);start=time.perf_counter();all_results=[];statuses=[];storage_errors=[]
    try:
        firm=read_firm(engine);prices=read_prices(engine);prices=prices.loc[prices.index<folds.loc[folds.split.eq('locked_test'),'decision_origin'].min()]
        inputs={k:hashlib.sha256(v.to_csv(index=False).encode()).hexdigest() for k,v in firm.items()}
        inputs['postgresql_price_history']=hashlib.sha256(prices.to_csv().encode()).hexdigest()
        if inputs!=pilot_manifest['input_hashes']:raise ValueError('PostgreSQL girdileri pilottan farklı.')
        experiment='development04_60s_'+hashlib.sha256(json.dumps([config,inputs,sources],sort_keys=True).encode()).hexdigest()[:16]
        if existing:
            prior=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
            if prior['experiment_id']!=experiment or prior['source_hashes']!=sources or prior['input_hashes']!=inputs:raise ValueError('Resume ayar/kaynak/girdileri aynı değil.')
            start-=max(0.,time.time()-prior['started_unix'])
        else:
            output.mkdir(parents=True);(output/'config_snapshot.json').write_bytes(config_path.read_bytes())
        schedule=[dict(week=w,run_key=k) for w in weeks for k in ['oracle']+[f'{s}_d{d}' for d in (0,1,2) for s in config['forecast_sources']]]
        if not existing:pd.DataFrame(schedule).to_csv(output/'planned_runs.csv',index=False,encoding='utf-8-sig')
        if not existing:write_json(output/'manifest.json',dict(experiment_id=experiment,weeks=weeks,source_hashes=sources,input_hashes=inputs,
                   preserved_files=preserved,approved_weeks=34,milp_runs_planned=340,previous_pilot_plans_used=False,
                   locked_test_evaluated=False,seed_experiment=False,task5=False,stochastic_mode=False,started_unix=time.time()))
        write_json(output/'process.json',dict(pid=os.getpid(),experiment_id=experiment,state='running',resumed=existing))
        builder,_=load_builder(project/'src/firma_cizelgeleme.py')
        with keep_awake() as awake:
            write_json(output/'runtime_environment.json',dict(prevent_system_sleep_requested=awake))
            for index,week in enumerate(weeks,1):
                try:
                    if (output/week.strftime('%Y%m%d')/'week_checkpoint.json').exists():
                        result=json.loads((output/week.strftime('%Y%m%d')/'week_checkpoint.json').read_text(encoding='utf-8'))
                        state=json.loads((output/week.strftime('%Y%m%d')/'week_status.json').read_text(encoding='utf-8'))
                        for rows in result.values():
                            for row in rows:
                                if 'week' in row:row['week']=pd.Timestamp(row['week'])
                        print(f'RESTORED WEEK {index}; no solver repeated',flush=True)
                    else:result,state=week_run(project,output,week,firm,prices,config,builder)
                except Exception as error:
                    state=dict(week=week,complete=False,week_failed=True,error_type=type(error).__name__,reason=str(error))
                    write_json(output/week.strftime('%Y%m%d')/'week_fatal_error.json',state)
                    result=recover_fatal_week(output/week.strftime('%Y%m%d'),week,state)
                all_results.append(result);statuses.append(state)
                checkpoint(output,all_results,statuses)
                try:
                    if result['success'] and result['metrics']:upload(engine,experiment,result['success'],result['metrics'])
                    persist_aux(engine,experiment,result)
                except Exception as error:
                    storage_errors.append(dict(week=str(week),error_type=type(error).__name__,reason=str(error)))
                    write_json(output/'storage_errors.json',storage_errors)
                progress=dict(experiment_id=experiment,weeks_processed=index,weeks_complete=sum(s.get('complete',False) for s in statuses),
                    planned_weeks=34,elapsed_seconds=time.perf_counter()-start,successful_milp=sum(len(r['success']) for r in all_results),
                    failure_count=sum(s.get('failed_solves',0)+int(s.get('week_failed',False)) for s in statuses))
                write_json(output/'progress.json',progress)
                print(f"WEEK {index}/34 complete={state.get('complete',False)} elapsed={progress['elapsed_seconds']/60:.2f} min successful_MILP={progress['successful_milp']}",flush=True)
        # Yalnız SQL idempotans denetimi tekrarlanır; hiçbir solver koşumu tekrarlanmaz.
        success=[row for r in all_results for row in r['success']];metrics=[row for r in all_results for row in r['metrics']]
        if success and metrics:
            upload(engine,experiment,success,metrics);first=snapshot(engine,experiment)
            upload(engine,experiment,success,metrics)
            if first!=snapshot(engine,experiment):raise AssertionError('SQL idempotans kontrolü başarısız.')
        merged={k:[row for r in all_results for row in r[k]] for k in ['attempts','components','audits','best','tighter']}
        persist_aux(engine,experiment,merged);persist_aux(engine,experiment,merged)
        if tree_hashes(project,[pilot,project/'data/results/direct_milp_04_pilot',project/'data/results/direct_milp_04_incumbent_audit'])!=preserved:raise AssertionError('Pilot dosyaları değişti.')
        if any(digest(project/p)!=h for p,h in sources.items()):raise AssertionError('Çalışma kaynağı değişti.')
        parent.verify_lock(project,project/config['hgb_config'],project/config['parent_protocol'])
        completion=dict(experiment_id=experiment,elapsed_seconds=time.perf_counter()-start,stage='solves_complete',
            weeks_processed=34,weeks_complete=sum(s.get('complete',False) for s in statuses),successful_milp=len(success),
            planned_milp=340,storage_retry_history=storage_errors,sql_idempotent=True,pilots_preserved=True,
            locked_test_evaluated=False,seed_experiment=False,task5=False,stochastic_mode=False)
        write_json(output/'completion.json',completion)
        from full_report import report
        report_tables=report(output)
        persist_aux(engine,experiment,report_tables)
        completion['stage']='complete';write_json(output/'completion.json',completion)
        write_json(output/'process.json',dict(pid=os.getpid(),experiment_id=experiment,state='completed'))
        print('DEVELOPMENT STUDY FINISHED '+experiment,flush=True)
    finally:engine.dispose()


def checkpoint(output,results,statuses):
    names=dict(success='solver_runs',attempts='run_attempts',metrics='weekly_metrics',components='policy_cost_components',
               audits='full_model_audit',best='best_known_feasible',tighter='tightened_regret')
    for key,name in names.items():
        rows=[row for result in results for row in result[key]]
        if rows:
            frame=pd.DataFrame(rows)
            if 'solver_diagnostics' in frame:frame['solver_diagnostics']=frame['solver_diagnostics'].map(lambda x:json.dumps(x,ensure_ascii=False))
            frame.to_csv(output/f'{name}.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(statuses).to_csv(output/'week_status.csv',index=False,encoding='utf-8-sig')


def recover_fatal_week(folder,week,state):
    """Hafta sonu hatası önceki geçerli koşumları görünmez yapmamalı."""
    result=dict(success=[],attempts=[],metrics=[],components=[],audits=[],best=[],tighter=[])
    folder.mkdir(parents=True,exist_ok=True)
    keys=['oracle']+[f'{s}_d{d}' for d in (0,1,2) for s in ('hgb','ensemble','naive')]
    for key in keys:
        path=folder/key
        if (path/'run.json').exists():
            row=json.loads((path/'run.json').read_text(encoding='utf-8'));row['week']=week
            result['success'].append(row)
        if (path/'attempt.json').exists():
            attempt=json.loads((path/'attempt.json').read_text(encoding='utf-8'))
            if attempt['state']=='running':attempt.update(state='interrupted',reason='Week terminated before a verified run was saved.')
        else:attempt=dict(week=week,run_key=key,attempt=1,state='blocked_week_fatal',reason=state['reason'])
        result['attempts'].append(attempt)
    write_json(folder/'fatal_recovery.json',result)
    return result


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    parser.add_argument('--resume-pending',action='store_true')
    args=parser.parse_args();main(args.project.resolve(),args.output.resolve(),args.config.resolve(),args.resume_pending)
