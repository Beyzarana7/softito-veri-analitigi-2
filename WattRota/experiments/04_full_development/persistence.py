"""Haftalık yardımcı sonuçlar ve başarısızlıklar için idempotent, ayrı kayıt alanı."""
import json
import math
from sqlalchemy import text,bindparam
from sqlalchemy.dialects.postgresql import JSONB


def normalize(value):
    if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalize(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def persist_aux(engine,experiment_id,result):
    from kod.db import db_transaction
    keys={'attempts':['week','run_key','attempt'],'components':['week','policy'],'audits':['week','policy'],
          'best':['week'],'tighter':['week','policy'],'summary':['policy'],'ml_comparison':['week','mode','source']}
    records=[]
    for name,rows in result.items():
        if name not in keys:continue
        for row in rows:
            identity='|'.join(str(row.get(k,'')) for k in keys[name])
            payload=json.loads(json.dumps(normalize(row),default=str,allow_nan=False))
            records.append(dict(id=experiment_id,dataset=name,row_key=identity,payload=payload))
    if not records:return 0
    with db_transaction(engine,write=True) as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS results.milp_full_aux_04 (experiment_id text NOT NULL,dataset text NOT NULL,row_key text NOT NULL,payload jsonb NOT NULL,PRIMARY KEY(experiment_id,dataset,row_key))'))
        statement=text('INSERT INTO results.milp_full_aux_04 VALUES (:id,:dataset,:row_key,:payload) ON CONFLICT (experiment_id,dataset,row_key) DO UPDATE SET payload=EXCLUDED.payload WHERE results.milp_full_aux_04.payload IS DISTINCT FROM EXCLUDED.payload').bindparams(bindparam('payload',type_=JSONB))
        c.execute(statement,records)
        query=text('SELECT dataset,row_key,payload FROM results.milp_full_aux_04 WHERE experiment_id=:id ORDER BY dataset,row_key')
        before=c.execute(query,{'id':experiment_id}).all();c.execute(statement,records)
        assert before==c.execute(query,{'id':experiment_id}).all()
    return len(records)
