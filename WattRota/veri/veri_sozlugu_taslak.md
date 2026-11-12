# WattRota veri sözlüğü taslağı

PostgreSQL kataloglarından otomatik çıkarılmıştır. Şema: `wattrota`; zaman alanları Türkiye yerel zamanıdır. Bağlantı bilgileri bu dosyada bulunmaz.

## bakimlar

Birincil anahtar: kaynak_id, baslangic

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |
| baslangic | TIMESTAMP | Hayır | Evet |  |
| bitis | TIMESTAMP | Hayır |  |  |

Yabancı anahtarlar:
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)

## depo_kurallari

Birincil anahtar: depo_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| depo_id | TEXT | Hayır | Evet |  |
| toplam_kapasite_ton | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- Yok.

## elektrik_fiyatlari

Birincil anahtar: tarih_saat

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| tarih_saat | TIMESTAMP | Hayır | Evet |  |
| PTF (TL/MWh) | DOUBLE PRECISION | Hayır |  |  |

Yabancı anahtarlar:
- Yok.

## fiyatlar

Birincil anahtar: tarih_saat

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| tarih_saat | TIMESTAMP | Hayır | Evet |  |
| PTF (TL/MWh) | DOUBLE PRECISION | Hayır |  |  |

Yabancı anahtarlar:
- Yok.

## is_emirleri

Birincil anahtar: is_emri_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| is_emri_id | TEXT | Hayır | Evet |  |
| urun_id | TEXT | Hayır |  | wattrota.urunler.urun_id |
| islem_turu | TEXT | Hayır |  |  |
| miktar_ton | BIGINT | Hayır |  |  |
| serbest_birakma | TIMESTAMP | Hayır |  |  |
| tamamlanma_siniri | TIMESTAMP | Hayır |  |  |
| bolunebilir | BOOLEAN | Hayır |  |  |

Yabancı anahtarlar:
- (urun_id) → wattrota.urunler (urun_id)

## is_emri_siparis_baglantisi

Birincil anahtar: is_emri_id, siparis_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| is_emri_id | TEXT | Hayır | Evet | wattrota.is_emirleri.is_emri_id |
| siparis_id | TEXT | Hayır | Evet | wattrota.siparisler.siparis_id |
| tahsis_ton | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- (is_emri_id) → wattrota.is_emirleri (is_emri_id)
- (siparis_id) → wattrota.siparisler (siparis_id)

## isletme_kurallari

Birincil anahtar: kaynak_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |
| minimum_uretim_saat | BIGINT | Hayır |  |  |
| minimum_durus_saat | BIGINT | Hayır |  |  |
| baslangicta_aktif | BOOLEAN | Hayır |  |  |
| baslangic_durum_suresi_saat | BIGINT | Hayır |  |  |
| baslangic_urun_ayari | TEXT | Hayır |  | wattrota.urunler.urun_id |
| baslatma_enerjisi_kwh | BIGINT | Hayır |  |  |
| baslatma_elektrik_disi_gider_tl | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- (baslangic_urun_ayari) → wattrota.urunler (urun_id)
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)

## kaynak_takvimi

Birincil anahtar: kaynak_id, tarih_saat

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |
| tarih_saat | TIMESTAMP | Hayır | Evet | wattrota.tesis_takvimi.tarih_saat |
| kullanilabilir | BOOLEAN | Hayır |  |  |

Yabancı anahtarlar:
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)
- (tarih_saat) → wattrota.tesis_takvimi (tarih_saat)

## kaynak_urun

Birincil anahtar: kaynak_id, urun_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |
| urun_id | TEXT | Hayır | Evet | wattrota.urunler.urun_id |
| kapasite_ton_saat | BIGINT | Hayır |  |  |
| calisma_gucu_kw | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)
- (urun_id) → wattrota.urunler (urun_id)

## kaynaklar

Birincil anahtar: kaynak_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| kaynak_id | TEXT | Hayır | Evet |  |
| kaynak_adi | TEXT | Hayır |  |  |
| kaynak_turu | TEXT | Hayır |  |  |

Yabancı anahtarlar:
- Yok.

## referans_plan

Birincil anahtar: kaynak_id, tarih_saat

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |
| tarih_saat | TIMESTAMP | Hayır | Evet | wattrota.tesis_takvimi.tarih_saat |
| durum | TEXT | Hayır |  |  |
| urun_id | TEXT | Evet |  | wattrota.urunler.urun_id |
| is_emri_id | TEXT | Evet |  | wattrota.is_emirleri.is_emri_id |

Yabancı anahtarlar:
- (is_emri_id) → wattrota.is_emirleri (is_emri_id)
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)
- (tarih_saat) → wattrota.tesis_takvimi (tarih_saat)
- (urun_id) → wattrota.urunler (urun_id)

## referans_yuklemeler

Birincil anahtar: siparis_id, kaynak_id, tarih_saat

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| siparis_id | TEXT | Hayır | Evet | wattrota.siparisler.siparis_id |
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |
| tarih_saat | TIMESTAMP | Hayır | Evet | wattrota.tesis_takvimi.tarih_saat |
| miktar_ton | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)
- (siparis_id) → wattrota.siparisler (siparis_id)
- (tarih_saat) → wattrota.tesis_takvimi (tarih_saat)

## rota_kaynaklari

Birincil anahtar: rota_id, adim_no, kaynak_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| rota_id | TEXT | Hayır | Evet | wattrota.rotalar.rota_id |
| adim_no | BIGINT | Hayır | Evet | wattrota.rotalar.adim_no |
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |

Yabancı anahtarlar:
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)
- (rota_id, adim_no) → wattrota.rotalar (rota_id, adim_no)

## rota_tanimlari

Birincil anahtar: rota_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| rota_id | TEXT | Hayır | Evet |  |
| urun_id | TEXT | Hayır |  | wattrota.urunler.urun_id |
| teslim_turu | TEXT | Hayır |  |  |

Yabancı anahtarlar:
- (urun_id) → wattrota.urunler (urun_id)

## rotalar

Birincil anahtar: rota_id, adim_no

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| rota_id | TEXT | Hayır | Evet | wattrota.rota_tanimlari.rota_id |
| urun_id | TEXT | Hayır |  | wattrota.rota_tanimlari.urun_id; wattrota.urunler.urun_id |
| teslim_turu | TEXT | Hayır |  | wattrota.rota_tanimlari.teslim_turu |
| adim_no | BIGINT | Hayır | Evet |  |
| islem_turu | TEXT | Hayır |  |  |
| girdi_stok_turu | TEXT | Hayır |  |  |
| cikti_stok_turu | TEXT | Hayır |  |  |

Yabancı anahtarlar:
- (rota_id, urun_id, teslim_turu) → wattrota.rota_tanimlari (rota_id, urun_id, teslim_turu)
- (urun_id) → wattrota.urunler (urun_id)

## siparisler

Birincil anahtar: siparis_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| siparis_id | TEXT | Hayır | Evet |  |
| urun_id | TEXT | Hayır |  | wattrota.rota_tanimlari.urun_id; wattrota.urunler.urun_id |
| miktar_ton | BIGINT | Hayır |  |  |
| teslim_turu | TEXT | Hayır |  | wattrota.rota_tanimlari.teslim_turu |
| rota_id | TEXT | Hayır |  | wattrota.rota_tanimlari.rota_id |
| gelis_zamani | TIMESTAMP | Hayır |  |  |
| en_erken_yukleme | TIMESTAMP | Hayır |  |  |
| teslim_zamani | TIMESTAMP | Hayır |  |  |

Yabancı anahtarlar:
- (rota_id, urun_id, teslim_turu) → wattrota.rota_tanimlari (rota_id, urun_id, teslim_turu)
- (urun_id) → wattrota.urunler (urun_id)

## stok_alanlari

Birincil anahtar: stok_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| stok_id | TEXT | Hayır | Evet |  |
| urun_id | TEXT | Hayır |  | wattrota.urunler.urun_id |
| stok_turu | TEXT | Hayır |  |  |
| minimum_ton | BIGINT | Hayır |  |  |
| kapasite_ton | BIGINT | Hayır |  |  |
| baslangic_ton | BIGINT | Hayır |  |  |
| son_hedef_ton | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- (urun_id) → wattrota.urunler (urun_id)

## tesis_takvimi

Birincil anahtar: tarih_saat

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| tarih_saat | TIMESTAMP | Hayır | Evet |  |
| temel_yuk_kw | BIGINT | Hayır |  |  |
| guc_siniri_kw | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- Yok.

## urun_gecisleri

Birincil anahtar: kaynak_id, onceki_urun, sonraki_urun

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| kaynak_id | TEXT | Hayır | Evet | wattrota.kaynaklar.kaynak_id |
| onceki_urun | TEXT | Hayır | Evet | wattrota.urunler.urun_id |
| sonraki_urun | TEXT | Hayır | Evet | wattrota.urunler.urun_id |
| hazirlik_saat | BIGINT | Hayır |  |  |
| hazirlik_gucu_kw | BIGINT | Hayır |  |  |
| elektrik_disi_gider_tl | BIGINT | Hayır |  |  |

Yabancı anahtarlar:
- (kaynak_id) → wattrota.kaynaklar (kaynak_id)
- (onceki_urun) → wattrota.urunler (urun_id)
- (sonraki_urun) → wattrota.urunler (urun_id)

## urunler

Birincil anahtar: urun_id

| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |
|---|---|---|---|---|
| urun_id | TEXT | Hayır | Evet |  |
| urun_adi | TEXT | Hayır |  |  |

Yabancı anahtarlar:
- Yok.

