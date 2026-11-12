"""Ortak seçeneklerde enerji-maliyet matrisi bağımsız tesis hesabıyla eşleşmeli."""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from ortak_plan_karsilastirmasi import arsivden_plan
from firma_cizelgeleme import firma_verisini_oku,maliyet_ve_ozet

if __name__=='__main__':
    folder=Path(sys.argv[1]) if len(sys.argv)>1 else proje/'data/results/ortak_plan_deneyi'
    v=firma_verisini_oku(proje)
    idx=pd.read_csv(folder/'plan_indeksi.csv');e=np.load(folder/'saatlik_enerji.npy')
    assert e.shape==(len(idx),72)
    assert idx.iloc[0]['diger_kaynaklar']==idx.iloc[0]['H02_kaynagi']==idx.iloc[0]['yukleme_kaynagi']=='referans'
    v['fiyatlar']['PTF (TL/MWh)']=np.linspace(0,4000,72)
    for i,r in idx.iterrows():
        p,y=arsivden_plan(folder,r['plan_id'],pd.Timestamp('2025-10-06'),pd.Timestamp('2025-10-06'))
        o=maliyet_ve_ozet(v,p,y)[-1]
        maliyet=e[i]@v['fiyatlar']['PTF (TL/MWh)'].to_numpy()/1000+r['elektrik_disi_gider_tl']
        assert np.isclose(o.iloc[-1],maliyet,atol=0.02,rtol=0)
    k=pd.read_csv(folder/'haftalik_kararlar.csv')
    assert not k.duplicated(['karar_zamani','model']).any()
    assert k['bagimsiz_kontrol'].all()
    assert (k['havuz_minimumuna_fark_tl']>=-0.02).all()
    assert k.groupby('karar_zamani')['havuz_gercek_minimum_maliyet_tl'].nunique().eq(1).all()
    assert k['karar_zamani'].nunique()==44
    print(f'{len(idx)} ortak planin fiziksel ve matris maliyetleri eslesti; 44 haftanin karsilastirmasi tutarli.')
