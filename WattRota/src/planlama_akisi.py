"""Firma girdilerinden doğrulanmış çizelge ve maliyet karşılaştırması üretir."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from firma_cizelgeleme import firma_verisini_oku, firma_cizelgele, maliyet_ve_ozet
from fiyat_tahmini import elektrik_fiyatlarini_oku, fiyat_tahmini_uret
from fiyat_tahmini_gelistirme import gelistirilmis_tahmin

YONTEMLER = ('aciklanmis', 'basit', 'ml')


def planlama_girdisini_hazirla(firma, fiyat_gecmisi, yontem):
    """Tahminli kullanımda ilk günün sonrasındaki fiyatları bilgi kümesinden çıkarır."""
    if yontem not in YONTEMLER:
        raise ValueError('Yöntem aciklanmis, basit veya ml olmalı.')
    saatler = pd.DatetimeIndex(firma['tesis_takvimi']['tarih_saat'])
    if len(saatler) != 72 or not saatler.equals(pd.date_range(saatler.min(), periods=72, freq='h')):
        raise ValueError('Firma takvimi sıralı ve kesintisiz 72 saat olmalı.')
    karar = saatler[0]
    if karar != karar.normalize():
        raise ValueError('Firma takvimi gün başlangıcında başlamalı.')
    if fiyat_gecmisi.index.has_duplicates or not fiyat_gecmisi.index.is_monotonic_increasing:
        raise ValueError('Fiyat geçmişi sıralı ve benzersiz olmalı.')

    if yontem == 'aciklanmis':
        kullanilan = fiyat_gecmisi.reindex(saatler)
        kaynak = ['aciklanmis'] * 72
        bilgi = {'model': 'aciklanmis_fiyat', 'bilinen_saat': 72}
    else:
        bilinen = fiyat_gecmisi.loc[fiyat_gecmisi.index < karar + pd.Timedelta(days=1)].copy()
        if yontem == 'basit':
            tahmin, bilgi = fiyat_tahmini_uret(bilinen, karar, 'son_yayinlanan_gun')
        else:
            tahmin, bilgi = gelistirilmis_tahmin(bilinen, karar, 'hgb_duzeltme_365')
        kullanilan = pd.concat([bilinen.reindex(saatler[:24]), tahmin]).reindex(saatler)
        kaynak = ['aciklanmis'] * 24 + ['tahmin'] * 48
        bilgi = dict(bilgi, bilinen_saat=24)
    if not np.isfinite(kullanilan).all() or (kullanilan < 0).any():
        raise ValueError('Planlama dönemi için geçerli fiyatlar eksik.')
    v = copy.deepcopy(firma)
    v['fiyatlar'] = pd.DataFrame({'tarih_saat': saatler, 'PTF (TL/MWh)': kullanilan.to_numpy()})
    fiyat_raporu = v['fiyatlar'].assign(bilgi_turu=kaynak)
    return v, fiyat_raporu, bilgi


def planlamayi_calistir(proje_dizini, cikti_dizini, yontem='aciklanmis', sure=120,
                       goreli_acik=0.001, degisiklik_gideri=0.0):
    """Aynı firma ve fiyat koşullarında referans ile öneriyi karşılaştırır."""
    if not np.isfinite([sure, goreli_acik, degisiklik_gideri]).all():
        raise ValueError('Çözüm ayarları sonlu olmalı.')
    if sure <= 0 or not 0 <= goreli_acik < 1 or degisiklik_gideri < 0:
        raise ValueError('Süre pozitif, açık [0,1), değişiklik gideri negatif olmayan bir sayı olmalı.')
    proje = Path(proje_dizini)
    cikti = Path(cikti_dizini)
    if cikti.exists():
        raise FileExistsError('Sonuç klasörü zaten var; yeni bir klasör adı seçin.')
    firma = firma_verisini_oku(proje)
    fiyat = elektrik_fiyatlarini_oku(proje)
    v, fiyat_raporu, tahmin_bilgisi = planlama_girdisini_hazirla(firma, fiyat, yontem)
    referans = maliyet_ve_ozet(v, v['referans_plan'], v['referans_yuklemeler'], degisiklik_gideri)[-1]
    sonuc = firma_cizelgele(v, zaman_siniri=sure, goreli_acik=goreli_acik,
                           degisiklik_gideri=degisiklik_gideri)
    plan, yuklemeler, _, _, _, _, cozum = sonuc
    stok, faaliyet, saatlik, oneri = maliyet_ve_ozet(v, plan, yuklemeler, degisiklik_gideri)
    maliyet_alani = 'Karşılaştırılan toplam maliyet (TL)'
    if not np.isclose(oneri[maliyet_alani], cozum['maliyet_tl'], atol=0.02, rtol=0):
        raise ValueError('Bağımsız maliyet hesabı çözücü sonucuyla uyuşmuyor.')
    karsilastirma = pd.concat([referans.rename('Referans'), oneri.rename('Önerilen')], axis=1)
    karsilastirma.index.name = 'olcut'
    tablolar = dict(onerilen_plan=plan, onerilen_yuklemeler=yuklemeler,
                   stok_hareketleri=stok, faaliyetler=faaliyet, saatlik_sonuc=saatlik,
                   planlama_fiyatlari=fiyat_raporu)
    bilgi = dict(yontem=yontem, tahmin=tahmin_bilgisi, cozum=cozum,
                 planlama_maliyeti_avantaji_tl=float(referans[maliyet_alani] - oneri[maliyet_alani]),
                 bagimsiz_fiziksel_kontrol=True, bagimsiz_maliyet_kontrolu=True)

    # Gerçekleşmiş fiyatlar yalnız plan seçildikten sonra değerlendirmeye alınır.
    if yontem != 'aciklanmis':
        gercek = fiyat.reindex(pd.DatetimeIndex(v['fiyatlar']['tarih_saat']))
        if gercek.notna().all():
            degerleme = copy.deepcopy(v)
            degerleme['fiyatlar']['PTF (TL/MWh)'] = gercek.to_numpy()
            gercek_ref = maliyet_ve_ozet(degerleme, v['referans_plan'], v['referans_yuklemeler'], degisiklik_gideri)[-1]
            gercek_oneri = maliyet_ve_ozet(degerleme, plan, yuklemeler, degisiklik_gideri)[-1]
            tablolar['gerceklesen_karsilastirma'] = pd.concat(
                [gercek_ref.rename('Referans'), gercek_oneri.rename('Önerilen')], axis=1)
            tablolar['gerceklesen_karsilastirma'].index.name = 'olcut'
            bilgi['gerceklesen_maliyet_avantaji_tl'] = float(gercek_ref[maliyet_alani] - gercek_oneri[maliyet_alani])
    dosyalar = list((proje / 'data/synthetic/firma_01').glob('*.csv'))
    dosyalar += list((proje / 'data/raw/epias').glob('Piyasa_Takas_Fiyati-*.csv'))
    dosyalar += [proje / 'data/results/firma_01_veri_kontrolu' / f'{ad}.csv'
                 for ad in ('referans_plan', 'referans_yuklemeler')]
    dosyalar += [proje / 'src' / f'{ad}.py' for ad in
                 ('planlama_akisi', 'firma_verisi', 'firma_cizelgeleme', 'fiyat_tahmini', 'fiyat_tahmini_gelistirme')]
    bilgi['dosya_sha256'] = {str(p.relative_to(proje)): hashlib.sha256(p.read_bytes()).hexdigest() for p in dosyalar}
    cikti.mkdir(parents=True, exist_ok=False)
    for ad, tablo in tablolar.items():
        tablo.to_csv(cikti / f'{ad}.csv', index=ad == 'gerceklesen_karsilastirma', encoding='utf-8-sig')
    karsilastirma.to_csv(cikti / 'karsilastirma.csv', encoding='utf-8-sig')
    (cikti / 'sonuc.json').write_text(json.dumps(bilgi, ensure_ascii=False, indent=2), encoding='utf-8')
    return karsilastirma, bilgi
