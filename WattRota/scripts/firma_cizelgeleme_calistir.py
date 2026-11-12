"""Firma CSV'lerinden çizelge üretir ve bağımsız kontrolden sonra kaydeder."""
import argparse
import sys
from pathlib import Path
import pandas as pd

proje = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proje / 'src'))
from firma_cizelgeleme import firma_verisini_oku, firma_cizelgele, sonuc_paketini_kaydet, maliyet_ve_ozet

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sure', type=float, default=120, help='Ana arama süresi, saniye')
    parser.add_argument('--acik', type=float, default=0.001, help='Hedef göreli optimalite açığı')
    parser.add_argument('--degisiklik-gideri', type=float, default=0, help='Değişen üretim kaynak-saati başına TL')
    args = parser.parse_args()
    v=firma_verisini_oku(proje)
    baslangic=None
    klasor=proje/'data/results/firma_01_cizelgeleme'
    if (klasor/'onerilen_plan.csv').is_file() and (klasor/'onerilen_yuklemeler.csv').is_file():
        eski_plan=pd.read_csv(klasor/'onerilen_plan.csv',keep_default_na=False)
        eski_yuk=pd.read_csv(klasor/'onerilen_yuklemeler.csv')
        eski_plan['tarih_saat']=pd.to_datetime(eski_plan['tarih_saat'])
        eski_yuk['tarih_saat']=pd.to_datetime(eski_yuk['tarih_saat'])
        try:
            eski_maliyet=maliyet_ve_ozet(v,eski_plan,eski_yuk,args.degisiklik_gideri)[-1]['Karşılaştırılan toplam maliyet (TL)']
            ref_maliyet=maliyet_ve_ozet(v,v['referans_plan'],v['referans_yuklemeler'])[-1]['Karşılaştırılan toplam maliyet (TL)']
            if eski_maliyet<=ref_maliyet+0.02:
                baslangic=(eski_plan,eski_yuk)
        except (ValueError,KeyError):
            print('Kayıtlı plan güncel firma koşullarına uymuyor; referanstan başlanacak.')
    sonuc = firma_cizelgele(v, zaman_siniri=args.sure, goreli_acik=args.acik,
                           degisiklik_gideri=args.degisiklik_gideri,baslangic_cozumu=baslangic)
    print(sonuc_paketini_kaydet(proje, sonuc).round(2).to_string())
    print('Çözücü durumu:', sonuc[-1]['durum'])
    print('Göreli optimalite açığı (%):', round(100 * sonuc[-1]['goreli_acik'], 2))
