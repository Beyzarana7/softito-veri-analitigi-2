"""Teslim süresi nedeniyle durdurulan çalışmayı yalnız kaydedilmiş planlardan sonlandırır."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import highspy
import numpy as np
import pandas as pd


def dump(path,value):path.write_text(json.dumps(value,default=str,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(project,output):
    sys.path.extend([str(project),str(project/'src'),str(project/'experiments/04_direct_milp_60s'),str(project/'experiments/04_incumbent_audit'),str(project/'experiments/04_full_development')])
    from kod.db import create_db_engine,read_firm
    from firma_cizelgeleme import maliyet_ve_ozet
    from common import shift_firm,assert_prefix
    from model_audit import load_builder,evaluate,assert_same_model,tightened_regret
    from metrics import decision_metrics,aggregate_capture
    from costs import cost_breakdown,ADDITIVE
    from storage import upload,snapshot
    from persistence import persist_aux
    raw=project/'data/results/direct_milp_04_development_60s'
    manifest=json.loads((raw/'manifest.json').read_text(encoding='utf-8'))
    stopped=json.loads((raw/'early_stop.json').read_text(encoding='utf-8-sig'))
    if output.exists():raise FileExistsError('Teslim değerlendirmesi mevcut; üzerine yazılmadı.')
    for name,value in manifest['source_hashes'].items():
        if sha(project/name)!=value:raise ValueError('Çalışma kaynağı değişmiş: '+name)
    source_hashes={str(p.relative_to(raw)):sha(p) for p in raw.rglob('*') if p.is_file()}
    output.mkdir(parents=True);(output/'plans').mkdir();(output/'figures').mkdir()
    engine=create_db_engine(project)
    try:
        firm=read_firm(engine);builder,_=load_builder(project/'src/firma_cizelgeleme.py')
        expected=['oracle']+[f'{s}_d{d}' for d in (0,1,2) for s in ['hgb','ensemble','naive']]
        all_runs=[];all_metrics=[];all_parts=[];all_audits=[];all_best=[];all_tight=[];attempts=[];forecasts=[];actual_rows=[]
        complete=[];partial=[];not_started=[];issues=[]
        with patch.object(highspy,'Highs',side_effect=AssertionError('Teslim doğrulamasında optimizasyon başlatılamaz.')) as blocked:
            for w in manifest['weeks']:
                week=pd.Timestamp(w);folder=raw/week.strftime('%Y%m%d')
                if not folder.exists():not_started.append(str(week.date()));continue
                present=[k for k in expected if (folder/k/'run.json').exists()]
                if len(present)!=10:
                    partial.append(dict(week=str(week.date()),saved_runs=len(present),missing=[k for k in expected if k not in present]))
                    for key in present:
                        r=json.loads((folder/key/'run.json').read_text(encoding='utf-8'));r['week']=week
                        all_runs.append(r)
                    continue
                actual=pd.read_csv(folder/'oracle/planning_prices.csv',parse_dates=['tarih_saat'])
                v=shift_firm(firm,week);v['fiyatlar']=actual
                ref=maliyet_ve_ozet(v,v['referans_plan'],v['referans_yuklemeler'])
                reference_model=builder(v,zaman_siniri=1,yerel_iyilestirme=False)
                runs={};solutions={};validated={};history={}
                for key in expected:
                    f=folder/key;r=json.loads((f/'run.json').read_text(encoding='utf-8'));r['week']=week
                    p=pd.read_csv(f/'plan.csv',keep_default_na=False,parse_dates=['tarih_saat'])
                    y=pd.read_csv(f/'loads.csv',parse_dates=['tarih_saat'])
                    val=maliyet_ve_ozet(v,p,y)
                    if abs(float(val[-1]['Karşılaştırılan toplam maliyet (TL)'])-r['actual_cost_tl'])>.02:raise AssertionError('Kayıtlı maliyet farklı: '+key)
                    if r['requested_seed']!=42 or r['effective_seed']!=42 or r['time_limit_seconds']!=60:raise AssertionError('Ayar farklı.')
                    for stage in ['before_model','after_model','before_run','after_run']:
                        options=r['solver_diagnostics']['options'][stage]
                        if options['random_seed']['value']!=42 or options['threads']['value']!=1 or options['time_limit']['value']!=60:raise AssertionError('Etkin ayar farklı.')
                    current=(p,y,val[0]);source=r['source'];day=r['decision_day']
                    if source!='oracle':
                        if day>0:assert_prefix(history[source],current,week+pd.Timedelta(days=day))
                        history[source]=current
                    solutions[key]=(p,y);validated[key]=val;runs[key]=r
                    attempts.append(dict(week=week,run_key=key,attempt=1,state='success',evidence='verified saved run.json and independent revalidation'))
                policies={'reference':(v['referans_plan'],v['referans_yuklemeler'],ref),'oracle_incumbent':(*solutions['oracle'],validated['oracle'])}
                for s in ['hgb','ensemble','naive']:
                    policies[s+'_open']=(*solutions[s+'_d0'],validated[s+'_d0'])
                    pieces=[];loads=[]
                    for day in [0,1,2]:
                        p,y=solutions[f'{s}_d{day}'];lo=week+pd.Timedelta(days=day);hi=lo+pd.Timedelta(days=1)
                        pieces.append(p.loc[p.tarih_saat.ge(lo)&p.tarih_saat.lt(hi)]);loads.append(y.loc[y.tarih_saat.ge(lo)&y.tarih_saat.lt(hi)])
                    p=pd.concat(pieces,ignore_index=True);y=pd.concat(loads,ignore_index=True)
                    val=maliyet_ve_ozet(v,p,y)
                    policies[s+'_rolling']=(p,y,val)
                costs={}
                for policy,(p,y,val) in policies.items():
                    cost=float(val[-1]['Karşılaştırılan toplam maliyet (TL)'])
                    model=builder(v,zaman_siniri=1,yerel_iyilestirme=False,baslangic_cozumu=(p,y))
                    assert_same_model(reference_model,model);a=evaluate(model,cost)
                    if not a['full_model_feasible']:raise AssertionError(str(a['violations']))
                    all_audits.append(dict(week=week,policy=policy,**{k:x for k,x in a.items() if k!='violations'}))
                    costs[policy]=cost
                    dest=output/'plans'/week.strftime('%Y%m%d')/policy;dest.mkdir(parents=True)
                    for name,frame in [('plan',p),('loads',y),('stocks',val[0]),('activity',val[1]),('hourly_cost',val[2])]:
                        frame.to_csv(dest/(name+'.csv'),index=False,encoding='utf-8-sig')
                    parts=cost_breakdown(v,val)
                    all_parts.append(dict(week=week,policy=policy,**{k:float(parts[k].sum()) for k in ADDITIVE+['total_electricity_tl','total_cost_tl']}))
                lower=runs['oracle']['lower_bound_tl'];original_upper=runs['oracle']['actual_cost_tl'];upper=min(costs.values());ref_cost=costs['reference']
                all_best.append(dict(week=week,original_oracle_upper_tl=original_upper,oracle_lower_bound_tl=lower,
                    verified_best_known_feasible_cost_tl=upper,winning_policies=';'.join(p for p,c in costs.items() if abs(c-upper)<=.02),posthoc=True))
                for policy,cost in costs.items():
                    all_metrics.append(dict(week=week,policy=policy,reference_cost_tl=ref_cost,oracle_incumbent_tl=original_upper,
                       oracle_lower_bound_tl=lower,**decision_metrics(ref_cost,cost,original_upper,lower)))
                    low,high=tightened_regret(cost,lower,upper)
                    all_tight.append(dict(week=week,policy=policy,actual_cost_tl=cost,tightened_regret_lower_tl=low,tightened_regret_upper_tl=high,
                                          posthoc_upper_tl=upper,posthoc=True,independent_information_capture=None))
                for s in ['hgb','ensemble','naive']:
                    forecast=pd.read_csv(folder/f'{s}_d0/planning_prices.csv',parse_dates=['tarih_saat'])
                    for i,row in forecast.iterrows():
                        forecasts.append(dict(week=week,method=s,tarih_saat=row.tarih_saat,forecast_ptf=float(row['PTF (TL/MWh)']),
                                              actual_ptf=float(actual.iloc[i]['PTF (TL/MWh)']),announced=i<24))
                for _,r in actual.iterrows():actual_rows.append(dict(week=week,tarih_saat=r.tarih_saat,ptf_tl_mwh=float(r['PTF (TL/MWh)'])))
                all_runs.extend(runs.values());complete.append(str(week.date()))
                print(f'VALIDATED {week.date()} 10/10 solves; 8/8 full-model policies',flush=True)
            assert blocked.call_count==0
        metrics=pd.DataFrame(all_metrics);summary=[]
        for policy,f in metrics.groupby('policy'):
            summary.append(dict(policy=policy,evaluated_weeks=len(f),total_actual_cost_tl=float(f.actual_cost_tl.sum()),
                total_reference_cost_tl=float(f.reference_cost_tl.sum()),total_savings_tl=float(f.reference_advantage_tl.sum()),
                mean_regret_lower_tl=float(f.regret_lower_tl.mean()),mean_regret_upper_tl=float(f.regret_upper_tl.mean()),
                **aggregate_capture(float(f.reference_advantage_tl.sum()),float(f.potential_vs_incumbent_tl.sum()),float(f.potential_upper_tl.sum()))))
        comparison=[]
        for week,f in metrics.groupby('week'):
            f=f.set_index('policy')
            for mode in ['open','rolling']:
                for s in ['hgb','ensemble']:
                    naive=float(f.loc['naive_'+mode,'actual_cost_tl']);ml=float(f.loc[s+'_'+mode,'actual_cost_tl'])
                    comparison.append(dict(week=week,mode=mode,method=s,naive_cost_tl=naive,ml_cost_tl=ml,naive_minus_ml_tl=naive-ml))
        preds=pd.DataFrame(forecasts);scores=[]
        for method,f in preds.loc[~preds.announced].groupby('method'):
            error=f.forecast_ptf-f.actual_ptf
            scores.append(dict(method=method,forecast_hours=len(f),mae_tl_mwh=float(error.abs().mean()),rmse_tl_mwh=float(np.sqrt((error**2).mean()))))
        frames=dict(solver_runs=pd.DataFrame(all_runs).drop(columns=['solver_diagnostics'],errors='ignore'),weekly_metrics=metrics,
             method_summary=pd.DataFrame(summary),ml_vs_naive=pd.DataFrame(comparison),full_model_audit=pd.DataFrame(all_audits),
             best_known_feasible=pd.DataFrame(all_best),tightened_regret=pd.DataFrame(all_tight),policy_cost_components=pd.DataFrame(all_parts),
             forecasts=preds,forecast_scores=pd.DataFrame(scores),actual_prices=pd.DataFrame(actual_rows),run_attempts=pd.DataFrame(attempts))
        for name,f in frames.items():f.to_csv(output/(name+'.csv'),index=False,encoding='utf-8-sig')
        upload(engine,manifest['experiment_id'],all_runs,all_metrics);before=snapshot(engine,manifest['experiment_id'])
        upload(engine,manifest['experiment_id'],all_runs,all_metrics);assert before==snapshot(engine,manifest['experiment_id'])
        persist_aux(engine,manifest['experiment_id'],dict(attempts=attempts,components=all_parts,audits=all_audits,best=all_best,tighter=all_tight,
                      summary=summary,ml_comparison=[dict(r,source=r['method']) for r in comparison]))
        metadata=dict(parent_experiment_id=manifest['experiment_id'],stopped_early=True,stop_reason='delivery_deadline',
            planned_development_weeks=34,evaluated_weeks=len(complete),evaluated_week_starts=complete,
            evaluated_windows=[dict(start=w,end_exclusive=str(pd.Timestamp(w)+pd.Timedelta(hours=72))) for w in complete],
            partial_weeks=partial,not_started_development_weeks=not_started,remaining_development_weeks=34-len(complete),
            locked_test_weeks=10,locked_week_starts=['2026-08-31','2026-09-07','2026-09-14','2026-09-21','2026-09-28','2026-10-05','2026-10-12','2026-10-19','2026-10-26','2026-11-02'],
            locked_test_evaluated=False,selection_rule='chronological prefix completed before deadline; not selected by outcomes',
            solutions_revalidated=len(all_runs),full_model_policies=len(all_audits),violations=0,additional_solver_calls=0,
            sql_idempotent=True,original_process_exit='intentional termination after saved solution boundary',
            runtime_stop_record=stopped,task5='future work only; no sensitivity analysis',issues=issues)
        dump(output/'evaluation.json',metadata)
        dump(output/'review_manifest.json',dict(input_files_sha256=source_hashes,source_sha256=sha(Path(__file__)),
             reviewed_results_files_sha256={str(p.relative_to(output)):sha(p) for p in output.rglob('*.csv')}))
        for name,value in source_hashes.items():assert sha(raw/name)==value,'Raw changed: '+name
        dump(output/'partial_weeks.json',partial)
        print(json.dumps(metadata,ensure_ascii=False),flush=True)
        print(pd.DataFrame(summary).round(4).to_string(index=False),flush=True)
    finally:engine.dispose()


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.project.resolve(),a.output.resolve())
