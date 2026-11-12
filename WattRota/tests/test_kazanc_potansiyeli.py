"""Yeni başlangıçların uygunluğu, maliyet sınırları ve hata ayrıştırması."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from firma_cizelgeleme import firma_verisini_oku,maliyet_ve_ozet
from kazanc_potansiyeli import zipten_oku

if __name__=='__main__':
    folder=Path(sys.argv[1]) if len(sys.argv)>1 else proje/'data/results/kazanc_potansiyeli'
    v=firma_verisini_oku(proje);idx=pd.read_csv(folder/'blok_indeksi.csv');enerji=np.load(folder/'blok_enerji.npy')
    assert len(idx)==len(enerji) and enerji.shape[1]==72
    for i,r in idx.iterrows():
        p,y=zipten_oku(folder/'blok_baslangiclari.zip',r['plan_id'],pd.Timestamp('2025-10-06'))
        _,_,s,o=maliyet_ve_ozet(v,p,y)
        np.testing.assert_allclose(enerji[i],s['toplam_enerji_kwh'])
        assert np.isclose(r['elektrik_disi_gider_tl'],s['elektrik_disi_gider_tl'].sum(),atol=1e-6)
    aralik=pd.read_csv(folder/'kazanc_araliklari.csv')
    assert len(aralik)==3
    assert (aralik['matematiksel_alt_sinir_tl']<=aralik['bulunan_en_iyi_maliyet_tl']+0.02).all()
    assert (aralik['bulunan_en_iyi_maliyet_tl']<=aralik['referans_maliyet_tl']+0.02).all()
    np.testing.assert_allclose(aralik['bulunan_avantaj_tl'],aralik['referans_maliyet_tl']-aralik['bulunan_en_iyi_maliyet_tl'])
    t=pd.read_csv(folder/'ikili_plan_teshisi.csv',parse_dates=['karar_zamani'])
    h=pd.read_csv(folder/'saatlik_karar_hatasi.csv',parse_dates=['karar_zamani','tarih_saat'])
    etki=h.groupby(['karar_zamani','model'])['fiyat_hatasi_karar_farki_etkisi_tl'].sum()
    for r in t.itertuples(index=False):
        assert np.isclose(etki.loc[(r.karar_zamani,r.model)],r.tahmine_gore_iyilestirme_tl-r.gercek_iyilestirme_tl,atol=0.02,rtol=0)
    bilinen=h['tarih_saat']<h['karar_zamani']+pd.Timedelta(hours=24)
    assert h.loc[bilinen,'fiyat_hatasi_karar_farki_etkisi_tl'].abs().max()<1e-8
    k=pd.read_csv(folder/'kural_teshis_araliklari.csv')
    assert set(k['tani'])=={'stok_alt_siniri','ic_is_emri_sureleri','minimum_blok_sureleri'}
    assert (k['kural_maliyet_etkisi_alt_tl']>=0).all()
    assert (k['kural_maliyet_etkisi_alt_tl']<=k['kural_maliyet_etkisi_ust_tl']+0.02).all()
    eski=json.loads((proje/'data/results/tahmin_gelistirme/deney_izleri.json').read_text(encoding='utf-8'))
    for ad,expected in eski.items():
        if ad.startswith('data\\synthetic\\firma_01\\'):
            assert hashlib.sha256((proje/ad).read_bytes()).hexdigest()==expected
    print(f'{len(idx)} baslangic plani dogrulandi; maliyet araliklari ve saatlik hata ozdesligi gecti; asil firma CSVleri korunuyor.')
