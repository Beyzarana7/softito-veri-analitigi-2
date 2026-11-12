"""Senaryo dönüşümleri ve kesin yükleme kapasitesi çelişkisi."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from firma_senaryolari import senaryolari_hazirla,yukleme_kapasitesini_kontrol_et
from firma_verisi import firma_planini_dogrula
from firma_cizelgeleme import firma_verisini_oku

if __name__=='__main__':
    temel=firma_verisini_oku(proje)
    cases=senaryolari_hazirla(proje)
    for ad,c in cases.items():
        v=c['veriler']
        pd.testing.assert_frame_equal(v['kaynak_urun'],temel['kaynak_urun'])
        pd.testing.assert_frame_equal(v['isletme_kurallari'],temel['isletme_kurallari'])
        pd.testing.assert_frame_equal(v['stok_alanlari'],temel['stok_alanlari'])
        bag=v['is_emri_siparis_baglantisi'].groupby('is_emri_id')['tahsis_ton'].sum()
        assert np.allclose(v['is_emirleri']['miktar_ton'],v['is_emirleri']['is_emri_id'].map(bag))
        kapasite=yukleme_kapasitesini_kontrol_et(v)
        if ad=='kapasite_asimi':
            ihlal=kapasite[kapasite['kapasite_celiskisi']]
            assert len(ihlal)==1
            assert ihlal.iloc[0]['zorunlu_saat_alt_siniri']==12
            assert ihlal.iloc[0]['uygun_saat']==10
        else:
            assert not kapasite['kapasite_celiskisi'].any()
            firma_planini_dogrula(v)
        if ad.endswith('fiyatlari'):
            assert len(v['fiyatlar'])==72
            assert v['fiyatlar']['tarih_saat'].min().day_of_week==0
            assert v['siparisler']['miktar_ton'].sum()==6720
        if ad=='yogun_dokme_talep':
            assert v['siparisler']['miktar_ton'].sum()==6880
            satir=kapasite[(kapasite['kaynak_id']=='Y01')&(kapasite['gun']==pd.Timestamp('2025-10-07'))].iloc[0]
            assert satir['zorunlu_saat_alt_siniri']==satir['uygun_saat']==9
    pd.testing.assert_frame_equal(firma_verisini_oku(proje)['siparisler'],temel['siparisler'])
    print('5 senaryonun referansi dogrulandi; kapasite asiminda 12 > 10 saat celiskisi bulundu; temel firma korunuyor.')
