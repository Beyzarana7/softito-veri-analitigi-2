"""Firma veri setinin kaynak, rota, stok ve iş emri kontrolleri."""
import sys
from pathlib import Path
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from firma_verisi import firma_verisini_olustur,firma_planini_dogrula,hata_kontrolleri

if __name__=='__main__':
    v=firma_verisini_olustur(proje)
    h,f,s=firma_planini_dogrula(v)
    assert len(v['siparisler'])==18 and len(v['is_emirleri'])==18
    assert v['siparisler']['miktar_ton'].sum()==6720
    assert f.loc[f['kaynak_id'].isin(['H01','H02']),'miktar_ton'].sum()==6720
    assert f.loc[f['kaynak_id']=='P01','miktar_ton'].sum()==2880
    tests=hata_kontrolleri(v)
    assert len(tests)==13
    print('13 hatalı örnek reddedildi; referans plan ve malzeme dengesi doğrulandı.')

    # CSV'den yeniden yüklenen veriyle kontrolü tekrarlıyoruz.
    klasor=proje/'data/synthetic/firma_01'
    sonuc=proje/'data/results/firma_01_veri_kontrolu'
    tarih_alanlari={'tarih_saat','gelis_zamani','en_erken_yukleme','teslim_zamani','serbest_birakma','tamamlanma_siniri','baslangic','bitis'}
    geri={}
    for ad in v:
        dosya=(sonuc if ad.startswith('referans_') else klasor)/f'{ad}.csv'
        t=pd.read_csv(dosya,encoding='utf-8-sig',keep_default_na=False)
        for alan in tarih_alanlari.intersection(t.columns):
            t[alan]=pd.to_datetime(t[alan],format='%Y-%m-%d %H:%M:%S')
        geri[ad]=t
    hh,ff,ss=firma_planini_dogrula(geri)
    pd.testing.assert_frame_equal(h,hh,check_dtype=False)
    pd.testing.assert_frame_equal(f,ff,check_dtype=False)
    pd.testing.assert_frame_equal(s,ss,check_dtype=False)
    tekrar=firma_verisini_olustur(proje)
    for ad in v:
        pd.testing.assert_frame_equal(v[ad],tekrar[ad])
    print('CSV yeniden okuma ve deterministik yeniden üretim kontrolleri geçti.')
