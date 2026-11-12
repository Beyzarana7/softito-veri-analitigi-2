"""Firma CSV'lerini ilişkisel PostgreSQL tablolarına yükleyen SQL dosyasını hazırlar."""
from pathlib import Path
import sys

import pandas as pd

PROJE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJE / 'src'))
from firma_cizelgeleme import firma_verisini_oku
from firma_verisi import firma_planini_dogrula
from fiyat_tahmini import elektrik_fiyatlarini_oku

ANAHTARLAR = {
    'urunler': ['urun_id'], 'kaynaklar': ['kaynak_id'],
    'kaynak_urun': ['kaynak_id', 'urun_id'], 'stok_alanlari': ['stok_id'],
    'depo_kurallari': ['depo_id'], 'rota_tanimlari': ['rota_id'], 'rotalar': ['rota_id', 'adim_no'],
    'rota_kaynaklari': ['rota_id', 'adim_no', 'kaynak_id'],
    'siparisler': ['siparis_id'], 'is_emirleri': ['is_emri_id'],
    'is_emri_siparis_baglantisi': ['is_emri_id', 'siparis_id'],
    'isletme_kurallari': ['kaynak_id'],
    'urun_gecisleri': ['kaynak_id', 'onceki_urun', 'sonraki_urun'],
    'tesis_takvimi': ['tarih_saat'], 'kaynak_takvimi': ['kaynak_id', 'tarih_saat'],
    'bakimlar': ['kaynak_id', 'baslangic'], 'fiyatlar': ['tarih_saat'],
    'referans_plan': ['kaynak_id', 'tarih_saat'],
    'referans_yuklemeler': ['siparis_id', 'kaynak_id', 'tarih_saat'],
    'elektrik_fiyatlari': ['tarih_saat'],
}

# Tablolar, bağlı oldukları ana tabloların ardından oluşturulur.
SIRA = ['urunler', 'kaynaklar', 'kaynak_urun', 'stok_alanlari', 'depo_kurallari',
        'rota_tanimlari', 'rotalar', 'rota_kaynaklari', 'siparisler', 'is_emirleri',
        'is_emri_siparis_baglantisi', 'isletme_kurallari', 'urun_gecisleri',
        'tesis_takvimi', 'kaynak_takvimi', 'bakimlar', 'fiyatlar',
        'referans_plan', 'referans_yuklemeler', 'elektrik_fiyatlari']

EK_KURALLAR = {
    'kaynak_urun': ['CHECK (kapasite_ton_saat > 0 AND calisma_gucu_kw >= 0)'],
    'stok_alanlari': ['UNIQUE (urun_id, stok_turu)',
        'CHECK (minimum_ton >= 0 AND minimum_ton <= baslangic_ton AND baslangic_ton <= kapasite_ton)',
        'CHECK (son_hedef_ton >= minimum_ton AND son_hedef_ton <= kapasite_ton)'],
    'depo_kurallari': ['CHECK (toplam_kapasite_ton > 0)'],
    'rota_tanimlari': ['UNIQUE (rota_id, urun_id, teslim_turu)'],
    'rotalar': ['CHECK (adim_no > 0)'],
    'siparisler': ['CHECK (miktar_ton > 0)',
        'CHECK (gelis_zamani <= en_erken_yukleme AND en_erken_yukleme < teslim_zamani)'],
    'is_emirleri': ['CHECK (miktar_ton > 0 AND serbest_birakma < tamamlanma_siniri)'],
    'is_emri_siparis_baglantisi': ['CHECK (tahsis_ton > 0)'],
    'isletme_kurallari': ['CHECK (minimum_uretim_saat >= 1 AND minimum_durus_saat >= 1)',
        'CHECK (baslangic_durum_suresi_saat >= 0 AND baslatma_enerjisi_kwh >= 0 AND baslatma_elektrik_disi_gider_tl >= 0)'],
    'urun_gecisleri': ['CHECK (onceki_urun <> sonraki_urun)',
        'CHECK (hazirlik_saat >= 1 AND hazirlik_gucu_kw >= 0 AND elektrik_disi_gider_tl >= 0)'],
    'tesis_takvimi': ['CHECK (temel_yuk_kw >= 0 AND guc_siniri_kw >= temel_yuk_kw)'],
    'bakimlar': ['CHECK (baslangic < bitis)'],
    'fiyatlar': ['CHECK ("PTF (TL/MWh)" >= 0)'],
    'elektrik_fiyatlari': ['CHECK ("PTF (TL/MWh)" >= 0)'],
    'referans_plan': ["CHECK (durum IN ('uretim', 'hazirlik', 'kapali'))",
        "CHECK ((durum = 'uretim' AND urun_id IS NOT NULL AND is_emri_id IS NOT NULL) OR (durum = 'hazirlik' AND urun_id IS NOT NULL AND is_emri_id IS NULL) OR (durum = 'kapali' AND urun_id IS NULL AND is_emri_id IS NULL))"],
    'referans_yuklemeler': ['CHECK (miktar_ton > 0)'],
}


def ad(alan):
    return '"' + alan.replace('"', '""') + '"'


def deger(x):
    if pd.isna(x) or x == '':
        return 'NULL'
    if isinstance(x, bool):
        return 'TRUE' if x else 'FALSE'
    if isinstance(x, (int, float)):
        return str(x)
    return "'" + str(x).replace("'", "''") + "'"


def yabanci_anahtarlar(tablo, alanlar):
    kurallar = []
    for alan, hedef, hedef_alan in [
        ('urun_id', 'urunler', 'urun_id'), ('kaynak_id', 'kaynaklar', 'kaynak_id'),
        ('onceki_urun', 'urunler', 'urun_id'), ('sonraki_urun', 'urunler', 'urun_id'),
        ('baslangic_urun_ayari', 'urunler', 'urun_id'),
        ('is_emri_id', 'is_emirleri', 'is_emri_id'), ('siparis_id', 'siparisler', 'siparis_id')]:
        if alan in alanlar and tablo != hedef:
            kurallar.append(f'FOREIGN KEY ({ad(alan)}) REFERENCES wattrota.{ad(hedef)} ({ad(hedef_alan)})')
    if tablo == 'rota_kaynaklari':
        kurallar.append('FOREIGN KEY (rota_id, adim_no) REFERENCES wattrota.rotalar (rota_id, adim_no)')
    if tablo in ('rotalar', 'siparisler'):
        kurallar.append('FOREIGN KEY (rota_id, urun_id, teslim_turu) REFERENCES wattrota.rota_tanimlari (rota_id, urun_id, teslim_turu)')
    if tablo in ('kaynak_takvimi', 'referans_plan', 'referans_yuklemeler'):
        kurallar.append('FOREIGN KEY (tarih_saat) REFERENCES wattrota.tesis_takvimi (tarih_saat)')
    return kurallar


def sql_hazirla(proje=PROJE):
    firma = firma_verisini_oku(proje)
    firma_planini_dogrula(firma)
    firma['rota_tanimlari'] = firma['rotalar'][['rota_id', 'urun_id', 'teslim_turu']].drop_duplicates()
    fiyat = elektrik_fiyatlarini_oku(proje)
    firma['elektrik_fiyatlari'] = fiyat.rename_axis('tarih_saat').reset_index()
    satirlar = ['-- wattrota veritabanında çalıştırılır. Mevcut tablolar silinmez.',
                '-- Zamanlar Europe/Istanbul yerel saatidir.',
                "DO $$ BEGIN IF current_database() <> 'wattrota' THEN RAISE EXCEPTION 'Önce wattrota veritabanına bağlanın.'; END IF; END $$;",
                'BEGIN;', 'CREATE SCHEMA wattrota;']
    for tablo in SIRA:
        df = firma[tablo]
        alanlar = []
        for alan in df:
            dtype = df[alan].dtype
            tip = ('timestamp without time zone' if pd.api.types.is_datetime64_any_dtype(dtype)
                   else 'boolean' if pd.api.types.is_bool_dtype(dtype)
                   else 'bigint' if pd.api.types.is_integer_dtype(dtype)
                   else 'double precision' if pd.api.types.is_float_dtype(dtype) else 'text')
            bos_olabilir = tablo == 'referans_plan' and alan in ('urun_id', 'is_emri_id')
            alanlar.append(f'{ad(alan)} {tip}' + ('' if bos_olabilir else ' NOT NULL'))
        alanlar += ['PRIMARY KEY (' + ', '.join(map(ad, ANAHTARLAR[tablo])) + ')']
        alanlar += yabanci_anahtarlar(tablo, df.columns)
        alanlar += EK_KURALLAR.get(tablo, [])
        satirlar.append(f'CREATE TABLE wattrota.{ad(tablo)} (\n    ' + ',\n    '.join(alanlar) + '\n);')
        kayitlar = list(df.itertuples(index=False, name=None))
        for bas in range(0, len(kayitlar), 500):
            values = ',\n'.join('(' + ', '.join(map(deger, r)) + ')' for r in kayitlar[bas:bas + 500])
            satirlar.append(f'INSERT INTO wattrota.{ad(tablo)} VALUES\n{values};')
        satirlar.append(f"DO $$ BEGIN IF (SELECT count(*) FROM wattrota.{ad(tablo)}) <> {len(df)} THEN RAISE EXCEPTION '{tablo}: kayıt sayısı uyuşmuyor'; END IF; END $$;")
    satirlar += ['COMMIT;']
    ozet = [f"SELECT '{t}' AS tablo, count(*) AS aktarilan_kayit, {len(firma[t])} AS beklenen_kayit FROM wattrota.{ad(t)}" for t in SIRA]
    satirlar.append('\nUNION ALL\n'.join(ozet) + ';')
    cikti = proje / 'data/database_import/firma_01_yukle.sql'
    cikti.parent.mkdir(parents=True, exist_ok=True)
    cikti.write_text('\n\n'.join(satirlar), encoding='utf-8')
    print(cikti)
    print('Tablo sayısı:', len(SIRA), '| Elektrik fiyatı sayısı:', len(fiyat))
    return cikti


if __name__ == '__main__':
    sql_hazirla()
