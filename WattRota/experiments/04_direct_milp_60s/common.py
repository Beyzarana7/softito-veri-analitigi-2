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


