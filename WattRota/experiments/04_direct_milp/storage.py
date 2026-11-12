"""Pilot sonuçlarını ayrı results tablolarına tekrar oluşturmadan kaydeder."""
import json

from sqlalchemy import Column,DateTime,Float,MetaData,String,Table,Boolean,Integer,select,text,or_
from sqlalchemy.dialects.postgresql import JSONB,insert
from kod.db import db_transaction

metadata=MetaData(schema='results')
runs=Table('milp_runs_04',metadata,
    Column('experiment_id',String,primary_key=True),Column('week',DateTime,primary_key=True),
    Column('run_key',String,primary_key=True),Column('decision_day',Integer,nullable=False),
    Column('solver_status',String,nullable=False),Column('time_limit_reached',Boolean,nullable=False),
    Column('mip_gap',Float,nullable=False),Column('lower_bound_tl',Float,nullable=False),
    Column('solver_seconds',Float,nullable=False),Column('wall_seconds',Float,nullable=False),
    Column('time_limit_seconds',Float,nullable=False),Column('actual_cost_tl',Float,nullable=False),
    Column('expected_cost_tl',Float,nullable=False),Column('fixed_prefix_hours',Integer,nullable=False),
    Column('independent_validation',Boolean,nullable=False),Column('payload',JSONB,nullable=False))
weekly=Table('milp_weekly_04',metadata,
    Column('experiment_id',String,primary_key=True),Column('week',DateTime,primary_key=True),
    Column('policy',String,primary_key=True),Column('actual_cost_tl',Float,nullable=False),
    Column('oracle_incumbent_gap_tl',Float,nullable=False),Column('exact_regret_tl',Float),
    Column('regret_lower_tl',Float,nullable=False),Column('regret_upper_tl',Float,nullable=False),
    Column('oracle_exact_certified',Boolean,nullable=False),Column('payload',JSONB,nullable=False))


def json_clean(value):
    return json.loads(json.dumps(value,default=str,allow_nan=False))


def upload(engine,experiment_id,run_rows,week_rows):
    with db_transaction(engine,write=True) as conn:
        conn.execute(text('CREATE SCHEMA IF NOT EXISTS results'));metadata.create_all(conn)
        for table,rows in [(runs,run_rows),(weekly,week_rows)]:
            records=[]
            names=[c.name for c in table.columns if c.name not in ('experiment_id','payload')]
            for row in rows:
                records.append(dict(experiment_id=experiment_id,**{name:row[name] for name in names},payload=json_clean(row)))
            statement=insert(table).values(records)
            fields=[c.name for c in table.columns if not c.primary_key]
            conn.execute(statement.on_conflict_do_update(index_elements=[c.name for c in table.primary_key],
                         set_={name:statement.excluded[name] for name in fields},
                         where=or_(*[table.c[name].is_distinct_from(statement.excluded[name]) for name in fields])))


def snapshot(engine,experiment_id):
    with db_transaction(engine) as conn:
        return {table.name:[dict(row) for row in conn.execute(select(table).where(table.c.experiment_id==experiment_id).order_by(*list(table.primary_key))).mappings()]
                for table in (runs,weekly)}
