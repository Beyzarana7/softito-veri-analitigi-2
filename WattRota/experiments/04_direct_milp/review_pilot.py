"""Kaydedilmiş pilotun kontrolü, özet grafiği ve SQL yöntem özetleri."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import text,bindparam
from sqlalchemy.dialects.postgresql import JSONB


def review(project,output):
    sys.path.insert(0,str(project));sys.path.insert(0,str(project/'src'))
    from kod.db import create_db_engine,read_firm,read_prices,db_transaction
    from firma_cizelgeleme import maliyet_ve_ozet
    from run import shift_firm,assert_prefix,signature,old_pool_signatures
    from storage import upload,snapshot
    from forecasting import forecasts_at
    info=json.loads((output/'pilot_info.json').read_text(encoding='utf-8'))
    config=json.loads((output/'config_snapshot.json').read_text(encoding='utf-8'))
    from run import write_report
    runs=pd.read_csv(output/'solver_runs.csv',parse_dates=['week'])
    weekly=pd.read_csv(output/'weekly_metrics.csv',parse_dates=['week'])
    summary=pd.read_csv(output/'policy_summary.csv')
    assert len(runs)==28 and len(weekly)==24 and runs['week'].nunique()==4
    assert runs.groupby('week').size().eq(7).all()
    assert runs['time_limit_seconds'].eq(config['solver_time_limit_seconds']).all()
    assert runs['independent_validation'].all() and runs['violation_count'].eq(0).all()
    assert (weekly['actual_cost_tl']>=weekly['oracle_lower_bound_tl']-.02).all()
    engine=create_db_engine(project)
    try:
        firm=read_firm(engine);prices=read_prices(engine)
        verified=0;known_price_checks=0;pool=old_pool_signatures(project)
        outside=0
        for week,frame in runs.groupby('week'):
            v=shift_firm(firm,week)
            actual=prices.reindex(pd.date_range(week,periods=72,freq='h'))
            v['fiyatlar']=pd.DataFrame({'tarih_saat':actual.index,'PTF (TL/MWh)':actual.to_numpy()})
            history={}
            for row in frame.itertuples(index=False):
                folder=output/week.strftime('%Y%m%d')/row.run_key
                plan=pd.read_csv(folder/'plan.csv',keep_default_na=False,parse_dates=['tarih_saat'])
                loads=pd.read_csv(folder/'loads.csv',parse_dates=['tarih_saat'])
                costs=maliyet_ve_ozet(v,plan,loads)
                assert abs(float(costs[-1]['Karşılaştırılan toplam maliyet (TL)'])-row.actual_cost_tl)<.02
                current=(plan,loads,costs[0])
                novel=signature(plan,loads,week) not in pool
                outside+=int(novel)
                runs.loc[(runs['week']==week)&runs['run_key'].eq(row.run_key),'outside_19_plan_pool']=novel
                run_info=json.loads((folder/'run.json').read_text(encoding='utf-8'))
                run_info['outside_19_plan_pool']=novel
                (folder/'run.json').write_text(json.dumps(run_info,ensure_ascii=False,indent=2),encoding='utf-8')
                if row.source!='oracle':
                    if row.decision_day:
                        assert_prefix(history[row.source],current,week+pd.Timedelta(days=row.decision_day))
                    history[row.source]=current
                    planned=pd.read_csv(folder/'planning_prices.csv',parse_dates=['tarih_saat'])
                    cut=(row.decision_day+1)*24
                    np.testing.assert_allclose(planned['PTF (TL/MWh)'].iloc[:cut],actual.iloc[:cut],rtol=0,atol=1e-9)
                    known_price_checks+=1
                verified+=1
        # Gerçek model hattına yalnız tahmin anında bilinen fiyatlar ulaşmalı.
        origin=runs['week'].min();cut=origin+pd.Timedelta(days=1)
        safe=prices.loc[prices.index<cut].copy()
        poisoned=prices.loc[prices.index<origin+pd.Timedelta(days=3)].copy()
        poisoned.loc[poisoned.index>=cut]=1e9
        safe_forecasts,_=forecasts_at(safe,origin,project,config)
        poison_forecasts,_=forecasts_at(poisoned,origin,project,config)
        for source in ('hgb','ensemble'):
            np.testing.assert_array_equal(safe_forecasts[source].to_numpy(),poison_forecasts[source].to_numpy())
        runs.to_csv(output/'solver_runs.csv',index=False,encoding='utf-8-sig')
        info['outside_pool_runs']=outside
        (output/'pilot_info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        def clean_records(frame):
            return [{k:(None if pd.isna(v) else v) for k,v in r.items()} for r in frame.to_dict('records')]
        upload(engine,info['experiment_id'],clean_records(runs),clean_records(weekly))
        a=snapshot(engine,info['experiment_id'])
        upload(engine,info['experiment_id'],clean_records(runs),clean_records(weekly))
        assert a==snapshot(engine,info['experiment_id'])
        write_report(info,summary,output,config)
        # SQL özetleri aynı deney/politika anahtarıyla tekrar yazılabilir.
        with db_transaction(engine,write=True) as conn:
            conn.execute(text('CREATE TABLE IF NOT EXISTS results.milp_summary_04 (experiment_id text NOT NULL, policy text NOT NULL, payload jsonb NOT NULL, PRIMARY KEY (experiment_id,policy))'))
            statement=text('INSERT INTO results.milp_summary_04 VALUES (:experiment_id,:policy,:payload) ON CONFLICT (experiment_id,policy) DO UPDATE SET payload=EXCLUDED.payload WHERE results.milp_summary_04.payload IS DISTINCT FROM EXCLUDED.payload').bindparams(bindparam('payload',type_=JSONB))
            records=[dict(experiment_id=info['experiment_id'],policy=r['policy'],payload={k:(None if pd.isna(x) else x) for k,x in r.items()}) for r in summary.to_dict('records')]
            conn.execute(statement,records)
            before=conn.execute(text('SELECT policy,payload FROM results.milp_summary_04 WHERE experiment_id=:id ORDER BY policy'),{'id':info['experiment_id']}).all()
            conn.execute(statement,records)
            after=conn.execute(text('SELECT policy,payload FROM results.milp_summary_04 WHERE experiment_id=:id ORDER BY policy'),{'id':info['experiment_id']}).all()
            assert before==after and len(after)==6
        fig,axes=plt.subplots(2,1,figsize=(11,8),layout='constrained')
        order=['reference','oracle_incumbent','hgb_open','ensemble_open','hgb_rolling','ensemble_rolling']
        costs=weekly.pivot(index='week',columns='policy',values='actual_cost_tl').reindex(columns=order)
        costs.index=costs.index.strftime('%d.%m.%Y')
        costs.div(1000).plot.bar(ax=axes[0],rot=0)
        axes[0].set(xlabel='Geliştirme haftası',ylabel='Gerçek maliyet (bin TL)',title='Dört haftalık pilot — gerçekleşen maliyet')
        axes[0].legend(fontsize=8,ncol=3)
        s=summary.set_index('policy').loc[['hgb_open','ensemble_open','hgb_rolling','ensemble_rolling']]
        for i,(_,r) in enumerate(s.iterrows()):
            axes[1].plot([r['mean_regret_lower_tl'],r['mean_regret_upper_tl']],[i,i],marker='o')
        axes[1].set(yticks=range(len(s)),yticklabels=s.index,xlabel='Ortalama gerçek regret için alt–üst sınır (TL)',title='Oracle kesin optimum olmadığında regret aralığı')
        axes[1].grid(axis='x',alpha=.3)
        fig.savefig(output/'pilot_comparison.png',dpi=150);plt.close(fig)
        result=dict(saved_solutions_revalidated=verified,known_price_prefixes_checked=known_price_checks,
                    actual_forecast_future_poison_tests=2,sql_summary_rows=6,sql_summary_idempotent=True,
                    normalized_outside_pool_runs=outside)
        (output/'review_checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        postprocessing=dict(changes=['Undefined capture shown as undefined in report',
             'Plan hash normalizes integer/float tonnes; costs and schedules unchanged'],
             original_solver_manifest='manifest.json',milp_reruns=0,
             source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')})
        (output/'postprocessing_manifest.json').write_text(json.dumps(postprocessing,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    review(args.project.resolve(),args.output.resolve())
