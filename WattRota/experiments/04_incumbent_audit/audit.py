"""60 saniyelik pilotun deney sonrası fizibilite ve regret denetimi. Çözüm aramaz."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import highspy
import numpy as np
import pandas as pd

from model_audit import load_builder,evaluate,assert_same_model,tightened_regret


def write_json(path,value):path.write_text(json.dumps(value,default=str,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def hashes(project,folders):
    return {str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in folders for p in sorted(folder.rglob('*')) if p.is_file()}


def stitch(pilot,week,source):
    plans=[];loads=[]
    for day in (0,1,2):
        folder=pilot/week.strftime('%Y%m%d')/f'{source}_d{day}'
        p=pd.read_csv(folder/'plan.csv',keep_default_na=False,parse_dates=['tarih_saat'])
        y=pd.read_csv(folder/'loads.csv',parse_dates=['tarih_saat'],float_precision='round_trip')
        low=week+pd.Timedelta(days=day);high=low+pd.Timedelta(days=1)
        plans.append(p.loc[p.tarih_saat.ge(low)&p.tarih_saat.lt(high)])
        loads.append(y.loc[y.tarih_saat.ge(low)&y.tarih_saat.lt(high)])
    return pd.concat(plans,ignore_index=True),pd.concat(loads,ignore_index=True)


def load_policy(pilot,week,policy,firm):
    if policy=='reference':return firm['referans_plan'].copy(),firm['referans_yuklemeler'].copy()
    if policy.endswith('_rolling'):return stitch(pilot,week,policy.removesuffix('_rolling'))
    key='oracle' if policy=='oracle_incumbent' else policy.replace('_open','_d0')
    folder=pilot/week.strftime('%Y%m%d')/key
    return pd.read_csv(folder/'plan.csv',keep_default_na=False,parse_dates=['tarih_saat']),pd.read_csv(folder/'loads.csv',parse_dates=['tarih_saat'],float_precision='round_trip')


def shift_firm(firm,week):
    result={k:v.copy(deep=True) for k,v in firm.items()}
    delta=week-result['tesis_takvimi'].tarih_saat.min()
    for f in result.values():
        for column in f:
            if pd.api.types.is_datetime64_any_dtype(f[column]):f[column]+=delta
    return result


def diagnose(pilot,runs,firm,prices,maliyet):
    result=[]
    for row in runs.loc[runs.decision_day.eq(0)].itertuples(index=False):
        week=pd.Timestamp(row.week);v=shift_firm(firm,week)
        actual=prices.reindex(pd.date_range(week,periods=72,freq='h'))
        v['fiyatlar']=pd.DataFrame(dict(tarih_saat=actual.index,**{'PTF (TL/MWh)':actual.to_numpy()}))
        plan,loads=load_policy(pilot,week,'oracle_incumbent' if row.source=='oracle' else row.source+'_open',v)
        # Fiziksel eşitlik fiyat amaçlarından ayrı tutulur.
        rp=v['referans_plan'].sort_values(['kaynak_id','tarih_saat']).reset_index(drop=True)
        cp=plan.sort_values(['kaynak_id','tarih_saat']).reset_index(drop=True)
        same_machine=rp.equals(cp)
        a=v['referans_yuklemeler'].groupby(['siparis_id','kaynak_id','tarih_saat']).miktar_ton.sum()
        b=loads.groupby(['siparis_id','kaynak_id','tarih_saat']).miktar_ton.sum()
        ix=a.index.union(b.index);same_load=bool(np.allclose(a.reindex(ix,fill_value=0),b.reindex(ix,fill_value=0),atol=1e-6,rtol=0))
        planned=pd.read_csv(pilot/week.strftime('%Y%m%d')/row.run_key/'planning_prices.csv',parse_dates=['tarih_saat'])
        v['fiyatlar']=planned
        reference_objective=float(maliyet(v,v['referans_plan'],v['referans_yuklemeler'])[-1]['Karşılaştırılan toplam maliyet (TL)'])
        result.append(dict(week=week,run_key=row.run_key,source=row.source,solver_status=row.solver_status,
             solver_seconds=float(row.solver_seconds),time_limit_reached=bool(row.time_limit_reached),
             mip_node_count=int(row.mip_node_count),mip_gap=float(row.mip_gap),
             solver_objective_tl=float(row.solver_objective_tl),lower_bound_tl=float(row.lower_bound_tl),
             actual_cost_tl=float(row.actual_cost_tl),reference_planning_cost_tl=reference_objective,
             planning_improvement_tl=reference_objective-float(row.solver_objective_tl),
             objective_accounting_difference_tl=float(row.solver_objective_tl)-float(row.expected_cost_tl),
             same_machine_as_reference=same_machine,same_loading_as_reference=same_load,
             warm_start_api_acceptance_recorded=False,warm_start_validation_recorded=bool(row.independent_validation),
             feasible_solution_count=None,incumbent_history_available=False,bound_history_available=False,
             detailed_solver_log_available=False))
    return pd.DataFrame(result)


def persist(engine,audit_id,tables):
    from kod.db import db_transaction
    from sqlalchemy import text,bindparam
    from sqlalchemy.dialects.postgresql import JSONB
    with db_transaction(engine,write=True) as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS results.milp_posthoc_04 (audit_id text NOT NULL, dataset text NOT NULL, row_no integer NOT NULL, payload jsonb NOT NULL, PRIMARY KEY(audit_id,dataset,row_no))'))
        statement=text('INSERT INTO results.milp_posthoc_04 VALUES (:id,:dataset,:row_no,:payload) ON CONFLICT(audit_id,dataset,row_no) DO UPDATE SET payload=EXCLUDED.payload WHERE results.milp_posthoc_04.payload IS DISTINCT FROM EXCLUDED.payload').bindparams(bindparam('payload',type_=JSONB))
        records=[]
        for name,frame in tables.items():
            for i,row in enumerate(frame.to_dict('records')):
                row={k:(None if pd.isna(v) else v) for k,v in row.items()}
                records.append(dict(id=audit_id,dataset=name,row_no=i,payload=json.loads(json.dumps(row,default=str,allow_nan=False))))
        c.execute(statement,records)
        query=text('SELECT dataset,row_no,payload FROM results.milp_posthoc_04 WHERE audit_id=:id ORDER BY dataset,row_no')
        a=c.execute(query,{'id':audit_id}).all();c.execute(statement,records)
        assert a==c.execute(query,{'id':audit_id}).all() and len(a)==len(records)
    return len(records)


def run(project,output):
    if output.exists():raise FileExistsError('Denetim çıktısı mevcut; üzerine yazılmadı.')
    sys.path.insert(0,str(project));sys.path.insert(0,str(project/'src'))
    from kod.db import create_db_engine,read_firm,read_prices
    from firma_cizelgeleme import maliyet_ve_ozet
    pilot=project/'data/results/direct_milp_04_pilot_60s'
    preserved=hashes(project,[pilot,project/'experiments/04_direct_milp_60s'])
    manifest=json.loads((pilot/'manifest.json').read_text(encoding='utf-8'))
    weekly=pd.read_csv(pilot/'weekly_metrics.csv',parse_dates=['week'],float_precision='round_trip')
    runs=pd.read_csv(pilot/'solver_runs.csv',parse_dates=['week'],float_precision='round_trip')
    builder,origin=load_builder(project/'src/firma_cizelgeleme.py')
    engine=create_db_engine(project);output.mkdir(parents=True)
    try:
        firm=read_firm(engine);prices=read_prices(engine)
        prices=prices.loc[prices.index<pd.Timestamp('2026-08-31')]
        input_hashes={k:hashlib.sha256(v.to_csv(index=False).encode()).hexdigest() for k,v in firm.items()}
        input_hashes['postgresql_price_history']=hashlib.sha256(prices.to_csv().encode()).hexdigest()
        assert input_hashes==manifest['input_hashes']
        audits=[];best=[];tight=[];violations=[]
        with patch.object(highspy,'Highs',side_effect=AssertionError('Bu denetim HiGHS başlatamaz.')) as blocked:
            for week,frame in weekly.groupby('week'):
                v=shift_firm(firm,week);actual=prices.reindex(pd.date_range(week,periods=72,freq='h'))
                v['fiyatlar']=pd.DataFrame({'tarih_saat':actual.index,'PTF (TL/MWh)':actual.to_numpy()})
                reference_model=builder(v,zaman_siniri=1,yerel_iyilestirme=False)
                candidates=[]
                for row in frame.itertuples(index=False):
                    p,y=load_policy(pilot,week,row.policy,v)
                    try:
                        physical=maliyet_ve_ozet(v,p,y)
                        cost=float(physical[-1]['Karşılaştırılan toplam maliyet (TL)'])
                        matrix=builder(v,zaman_siniri=1,yerel_iyilestirme=False,baslangic_cozumu=(p,y))
                        assert_same_model(reference_model,matrix)
                        audit=evaluate(matrix,cost)
                        if abs(cost-float(row.actual_cost_tl))>.02:
                            audit['violations'].append(dict(kind='stored_policy_cost_mismatch',stored=float(row.actual_cost_tl),reconstructed=cost))
                            audit['full_model_feasible']=False
                        record=dict(week=week,policy=row.policy,independent_validation=True,unrestricted_original_model=True,
                            **{k:v for k,v in audit.items() if k!='violations'})
                        audits.append(record)
                        for violation in audit['violations']:violations.append(dict(week=str(week),policy=row.policy,**violation))
                        if audit['full_model_feasible']:
                            candidates.append((row.policy,cost))
                            if row.policy.endswith('_rolling'):
                                folder=output/week.strftime('%Y%m%d');folder.mkdir(parents=True,exist_ok=True)
                                p.to_csv(folder/f'{row.policy}_executed_plan.csv',index=False,encoding='utf-8-sig')
                                y.to_csv(folder/f'{row.policy}_executed_loads.csv',index=False,encoding='utf-8-sig')
                        print(f'{week.date()} {row.policy}: full_model={audit["full_model_feasible"]}; objective_diff={audit["objective_difference_tl"]:.9f}',flush=True)
                    except (ValueError,AssertionError) as error:
                        violations.append(dict(week=str(week),policy=row.policy,kind='candidate_build_or_physical',reason=str(error)))
                        audits.append(dict(week=week,policy=row.policy,independent_validation=False,full_model_feasible=False))
                upper=min(cost for _,cost in candidates)
                winners=[p for p,c in candidates if abs(c-upper)<=.02]
                lower=float(frame.iloc[0]['oracle_lower_bound_tl']);old_upper=float(frame.iloc[0]['oracle_incumbent_tl'])
                if lower>upper+.02:raise AssertionError('Oracle alt sınırı doğrulanmış uygun maliyeti aşıyor.')
                best.append(dict(week=week,original_oracle_upper_tl=old_upper,verified_best_known_feasible_cost_tl=upper,
                    oracle_lower_bound_tl=lower,improvement_over_oracle_incumbent_tl=old_upper-upper,
                    winning_policies=';'.join(winners),posthoc=True,independent_oracle_result=False,
                    bound_absolute_gap_tl=upper-lower,bound_relative_gap=(upper-lower)/abs(upper)))
                for row in frame.itertuples(index=False):
                    valid=next(a for a in audits if a['week']==week and a['policy']==row.policy)['full_model_feasible']
                    if not valid:continue
                    low,high=tightened_regret(float(row.actual_cost_tl),lower,upper)
                    tight.append(dict(week=week,policy=row.policy,actual_cost_tl=float(row.actual_cost_tl),
                        original_oracle_incumbent_gap_tl=float(row.actual_cost_tl)-old_upper,
                        old_regret_lower_tl=float(row.regret_lower_tl),old_regret_upper_tl=float(row.regret_upper_tl),
                        posthoc_verified_upper_tl=upper,oracle_lower_bound_tl=lower,
                        tightened_regret_lower_tl=low,tightened_regret_upper_tl=high,
                        lower_bound_tightening_tl=low-float(row.regret_lower_tl),
                        posthoc=True,independent_information_capture=None))
            assert blocked.call_count==0
        diagnostics=diagnose(pilot,runs,firm,prices,maliyet_ve_ozet)
        tables=dict(candidate_audit=pd.DataFrame(audits),best_known_feasible=pd.DataFrame(best),
                    tightened_regret=pd.DataFrame(tight),search_diagnostics=diagnostics)
        for name,frame in tables.items():frame.to_csv(output/f'{name}.csv',index=False,encoding='utf-8-sig')
        write_json(output/'violations.json',violations)
        audit_id='posthoc04_'+hashlib.sha256(json.dumps([manifest['experiment_id'],origin],sort_keys=True).encode()).hexdigest()[:16]
        sql_rows=persist(engine,audit_id,tables)
        assert hashes(project,[pilot,project/'experiments/04_direct_milp_60s'])==preserved
        proposal=dict(executed=False,fold_indices=[5,16,28],weeks=['2026-02-09','2026-04-27','2026-07-20'],
             seeds=[7,19,42,73,101],per_solve_seconds=60,threads=1,mip_relative_gap=.001,local_search=False,
             methods=['hgb','ensemble','naive'],per_week_seed_runs=10,total_milp_runs=150,
             solver_limits_sum_minutes=150,estimated_minutes_from_measured_pilot=1888.4165131000336/60*150/40,
             first_decision_shared_open_and_rolling=True,rolling_decisions=[0,1,2],
             warm_start='original reference at d0; own week/method/seed previous plan at d1,d2',
             freeze_forecasts_across_seeds=True,best_seed_selection=False,
             required_logging=['setSolution return status','effective seed before/after passModel and run',
                'incumbent event count and cost/time trace','primal/dual bound trace','node count','termination status',
                'full-model posthoc validation and accounting check'],
             reporting='All 15 week-seed pairs; paired ML-minus-naive and rolling-minus-open; equal-weight seed summaries; no best-of-seeds policy',
             unresolved='Rolling vs open still confounds information refresh with extra solve budget; no budget-matched control is run.')
        write_json(output/'rolling_seed_proposal.json',proposal)
        info=dict(audit_id=audit_id,parent_experiment_id=manifest['experiment_id'],model_source=origin,
             policies_checked=len(audits),rolling_candidates_checked=sum(a['policy'].endswith('_rolling') for a in audits),
             feasible_candidates=sum(a['full_model_feasible'] for a in audits),violation_count=len(violations),
             optimization_calls=0,sql_rows=sql_rows,sql_idempotent=True,raw_experiment_preserved=True,
             locked_test_evaluated=False,full_34_executed=False,seed_experiment_executed=False,task5_executed=False,
             preserved_hashes=preserved)
        write_json(output/'audit_info.json',info)
        from report import report
        report(output,tables,info,proposal)
        print(json.dumps({k:v for k,v in info.items() if k!='preserved_hashes'}),flush=True)
    finally:engine.dispose()


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.project.resolve(),a.output.resolve())
