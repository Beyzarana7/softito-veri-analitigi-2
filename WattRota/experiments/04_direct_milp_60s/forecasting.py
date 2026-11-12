"""HGB ve sabit ensemble; fiyat geçmişi yalnız PostgreSQL'den gelir."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def forecasts_at(prices,origin,project,config):
    sys.path.insert(0,str(project/'src'))
    origin=pd.Timestamp(origin)
    known=prices.loc[prices.index<origin+pd.Timedelta(hours=24)].copy()
    c2=json.loads((project/config['hgb_config']).read_text(encoding='utf-8'))
    c3=json.loads((project/config['ensemble_config']).read_text(encoding='utf-8'))
    parent=load_module(project/'experiments/02_walk_forward/protocol.py','task4_parent_protocol')
    model=load_module(project/'experiments/03_price_models/models.py','task4_point_models')
    spec=next(s for s in c2['models'] if s['id']=='hgb_residual_expanding')
    hgb,audit=parent.predict_expanding(known,origin,spec,c2,project)
    naive_spec=next(s for s in c2['models'] if s['id']=='son_yayinlanan_gun' and s['kind']=='naive')
    naive,naive_audit=parent.predict_expanding(known,origin,naive_spec,c2,project)
    pack=model.feature_pack(known,origin,c3)
    with threadpool_limits(limits=c3['threads']):
        linear,warnings=model.learner(pack,c3,'level',10.)
        light=model.level_only(pack,c3)
    if warnings:
        raise ValueError('Ensemble Lasso bileşeni yakınsamadı; tahmin kullanılmadı.')
    expected=['lear_level_10','lightgbm_level','hgb_expanding_cached']
    if c3['ensemble_level_components']!=expected:
        raise ValueError('Sabit ensemble tanımı değişmiş.')
    ensemble=np.mean([np.maximum(linear,0),light,hgb.to_numpy()],axis=0)
    return {'hgb':hgb,'ensemble':pd.Series(ensemble,index=hgb.index,name='prediction'),'naive':naive},{'hgb':audit,'naive':naive_audit,'ensemble_components':expected,'available_last':str(known.index.max())}


def planning_prices(actual,day,forecast=None):
    """Önce uygulanmış günler + bugün açıklanmış gün; yalnız kalan saatler tahmin."""
    if len(actual)!=72 or day not in (0,1,2):raise ValueError('72 saat ve gün 0/1/2 gerekli.')
    result=actual.copy()
    cut=(day+1)*24
    if cut<72:
        if forecast is None:raise ValueError('Bilinmeyen günler için tahmin gerekli.')
        selected=forecast.reindex(actual.index[cut:])
        if selected.isna().any() or not np.isfinite(selected).all():raise ValueError('Kalan ufuk tahmini eksik.')
        result.iloc[cut:]=selected.to_numpy()
    return result
