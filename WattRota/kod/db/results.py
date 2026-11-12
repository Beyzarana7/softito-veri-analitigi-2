"""Yalnız geliştirme sonuçlarını idempotent yükler; forecast_log canlı akışını bağlamaz."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String, Table,
                        CheckConstraint, func, select, text, or_)
from sqlalchemy.dialects.postgresql import JSONB, insert

from .engine import db_transaction

metadata=MetaData(schema='results')
weekly=Table('weekly_decision_metrics',metadata,
    Column('dataset_id',String,primary_key=True),Column('decision_origin',DateTime,primary_key=True),
    Column('model',String,primary_key=True),Column('selected_plan',String,nullable=False),
    Column('reference_cost_tl',Float,nullable=False),Column('selected_actual_cost_tl',Float,nullable=False),
    Column('pool_oracle_cost_tl',Float,nullable=False),Column('pool_regret_tl',Float,nullable=False),
    Column('information_capture',Float),Column('reference_advantage_tl',Float,nullable=False),
    Column('source_sha256',String(64),nullable=False),Column('payload',JSONB,nullable=False))
methods=Table('method_summaries',metadata,
    Column('dataset_id',String,primary_key=True),Column('model',String,primary_key=True),
    Column('weeks',Integer,nullable=False),Column('mean_cost_tl',Float,nullable=False),
    Column('mean_regret_tl',Float,nullable=False),Column('total_information_capture',Float),
    Column('source_sha256',String(64),nullable=False),Column('payload',JSONB,nullable=False))
savings=Table('net_savings',metadata,
    Column('dataset_id',String,primary_key=True),Column('record_key',String,primary_key=True),
    Column('reference_cost_tl',Float,nullable=False),Column('proposed_cost_tl',Float,nullable=False),
    Column('net_savings_tl',Float,nullable=False),Column('cost_basis',String,nullable=False),
    Column('source_sha256',String(64),nullable=False),Column('payload',JSONB,nullable=False))
forecast_log=Table('forecast_log',metadata,
    Column('generated_at',DateTime(timezone=True),primary_key=True),
    Column('target_time',DateTime(timezone=True),primary_key=True),
    Column('method',String,primary_key=True),Column('prediction',Float,nullable=False),
    CheckConstraint("prediction >= 0 AND prediction < 'Infinity'::double precision",name='forecast_prediction_finite_nonnegative'))


def ensure_results_schema(engine):
    with db_transaction(engine,write=True) as conn:
        conn.execute(text('CREATE SCHEMA IF NOT EXISTS results'))
        metadata.create_all(conn)
        conn.execute(text("""CREATE OR REPLACE FUNCTION results.reject_forecast_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              RAISE EXCEPTION 'forecast_log is append-only' USING ERRCODE = '55000';
            END $$"""))
        exists=conn.execute(text("SELECT 1 FROM pg_trigger WHERE tgname='forecast_log_append_only' AND tgrelid='results.forecast_log'::regclass AND NOT tgisinternal")).scalar()
        if not exists:
            conn.execute(text('CREATE TRIGGER forecast_log_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON results.forecast_log FOR EACH STATEMENT EXECUTE FUNCTION results.reject_forecast_mutation()'))


def payload(row):
    # JSONB'ye NaN/Infinity gönderilmez; CSV'deki tanımsız oranlar NULL kalır.
    result={}
    for key,value in row.items():
        if pd.isna(value): result[key]=None
        elif isinstance(value,(pd.Timestamp,)): result[key]=value.isoformat()
        elif isinstance(value,np.generic): result[key]=value.item()
        else: result[key]=value
    json.dumps(result,allow_nan=False)
    return result


def prepare_result_rows(project):
    project=Path(project)
    folder=project/'data/results/development_decisions_03'
    weekly_path=folder/'weekly_decision_metrics.csv'
    summary_path=folder/'model_summary.csv'
    source=project/'data/results/firma_01_cizelgeleme/karsilastirma.csv'
    hashes={str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (weekly_path,summary_path,source)}
    w=pd.read_csv(weekly_path,parse_dates=['decision_origin'])
    m=pd.read_csv(summary_path)
    folds=pd.read_csv(project/'data/results/walk_forward_02/folds.csv',parse_dates=['decision_origin'])
    permitted=set(folds.loc[folds['split'].eq('development'),'decision_origin'])
    if len(w)!=136 or set(w['decision_origin'])!=permitted or len(m)!=4:
        raise ValueError('Yalnız mühürlü 34 geliştirme haftasının dört yöntemi yüklenebilir.')
    if not w['independently_validated'].all():
        raise ValueError('Doğrulanmamış karar sonucu yüklenemez.')
    data_id='development_decisions_03'
    rows=[];net=[]
    for _,row in w.iterrows():
        item={k:row[k] for k in ('decision_origin','model','selected_plan','reference_cost_tl','selected_actual_cost_tl','pool_oracle_cost_tl','pool_regret_tl','reference_advantage_tl')}
        item.update(dataset_id=data_id,information_capture=None if pd.isna(row['information_capture']) else float(row['information_capture']),
                    source_sha256=hashes[str(weekly_path.relative_to(project))],payload=payload(row))
        rows.append(item)
        net.append(dict(dataset_id=data_id,record_key=f"{row['decision_origin'].isoformat()}|{row['model']}",
                        reference_cost_tl=row['reference_cost_tl'],proposed_cost_tl=row['selected_actual_cost_tl'],
                        net_savings_tl=row['reference_advantage_tl'],cost_basis='PTF_and_defined_costs_actual_prices_pool_selection',
                        source_sha256=item['source_sha256'],payload=payload(row)))
    summaries=[]
    for _,row in m.iterrows():
        summaries.append(dict(dataset_id=data_id,model=row['model'],weeks=int(row['weeks']),mean_cost_tl=float(row['mean_cost_tl']),
                              mean_regret_tl=float(row['mean_regret_tl']),total_information_capture=float(row['total_information_capture']),
                              source_sha256=hashes[str(summary_path.relative_to(project))],payload=payload(row)))
    comparison=pd.read_csv(source,index_col=0)
    metric='Karşılaştırılan toplam maliyet (TL)'
    ref=float(comparison.loc[metric,'Referans']);proposed=float(comparison.loc[metric,'Önerilen'])
    net.append(dict(dataset_id='firma_01_cizelgeleme',record_key='2025-10-06/2025-10-09',reference_cost_tl=ref,
                    proposed_cost_tl=proposed,net_savings_tl=ref-proposed,cost_basis='PTF_and_defined_costs_known_prices',
                    source_sha256=hashes[str(source.relative_to(project))],payload={'metric':metric,'period_start':'2025-10-06','period_end_exclusive':'2025-10-09'}))
    return [(weekly,rows),(methods,summaries),(savings,net)],hashes


def upsert_result_rows(engine,batches):
    with db_transaction(engine,write=True) as conn:
        for table,rows in batches:
            statement=insert(table).values(rows)
            names=[c.name for c in table.columns if not c.primary_key]
            statement=statement.on_conflict_do_update(index_elements=[c.name for c in table.primary_key],
                      set_={name:statement.excluded[name] for name in names},
                      where=or_(*[table.c[name].is_distinct_from(statement.excluded[name]) for name in names]))
            conn.execute(statement)


def result_counts(engine):
    with db_transaction(engine) as conn:
        return {t.name:int(conn.execute(select(func.count()).select_from(t)).scalar_one()) for t in (weekly,methods,savings,forecast_log)}
