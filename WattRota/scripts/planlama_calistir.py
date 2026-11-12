"""WattRota firma verilerini okuyarak doğrulanmış bir üretim planı oluşturur."""
import argparse
from datetime import datetime
from pathlib import Path
import sys

proje = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proje / 'src'))
from planlama_akisi import YONTEMLER, planlamayi_calistir


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yontem', choices=YONTEMLER, default='aciklanmis')
    parser.add_argument('--sure', type=float, default=120, help='Ana çözücü süresi; yerel iyileştirmeler ek süre alabilir.')
    parser.add_argument('--acik', type=float, default=0.001)
    parser.add_argument('--degisiklik-gideri', type=float, default=0)
    args = parser.parse_args()
    cikti = proje / 'data/results/planlama' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + args.yontem)
    try:
        tablo, bilgi = planlamayi_calistir(proje, cikti, args.yontem, args.sure,
                                          args.acik, args.degisiklik_gideri)
    except (ValueError, FileNotFoundError, FileExistsError) as hata:
        parser.exit(1, f'Planlama tamamlanamadı: {hata}\n')
    print(tablo.round(2).to_string())
    print('Çözücü durumu:', bilgi['cozum']['durum'])
    print('Optimalite açığı (%):', round(100 * bilgi['cozum']['goreli_acik'], 2))
    print('Planlama fiyatlarıyla maliyet avantajı (TL):', round(bilgi['planlama_maliyeti_avantaji_tl'], 2))
    if 'gerceklesen_maliyet_avantaji_tl' in bilgi:
        print('Gerçekleşmiş fiyatlarla maliyet avantajı (TL):', round(bilgi['gerceklesen_maliyet_avantaji_tl'], 2))
    print('Sonuç klasörü:', cikti)
