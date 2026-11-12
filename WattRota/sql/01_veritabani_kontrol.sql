-- wattrota veritabanında çalıştırılır. Test kayıtları kalıcı olarak eklenmez.
DO $$
BEGIN
    BEGIN
        INSERT INTO wattrota.urunler VALUES ('UR01', 'Tekrarlı test kaydı');
        RAISE EXCEPTION 'Tekrarlanan ürün kimliği kabul edildi.';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO wattrota.kaynak_urun VALUES ('H01', 'OLMAYAN_URUN', 60, 1800);
        RAISE EXCEPTION 'Olmayan ürün kabul edildi.';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        UPDATE wattrota.kaynak_urun SET kapasite_ton_saat = -1 WHERE kaynak_id = 'H01' AND urun_id = 'UR01';
        RAISE EXCEPTION 'Negatif kapasite kabul edildi.';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
END $$;

SELECT
    current_database() AS veritabani,
    (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'wattrota') AS tablo_sayisi,
    (SELECT count(*) FROM wattrota.siparisler) AS siparis_sayisi,
    (SELECT sum(miktar_ton) FROM wattrota.siparisler) AS toplam_siparis_ton,
    (SELECT sum(miktar_ton) FROM wattrota.referans_yuklemeler) AS referans_teslim_ton,
    (SELECT count(*) FROM wattrota.elektrik_fiyatlari) AS elektrik_fiyati_sayisi,
    (SELECT min(tarih_saat) FROM wattrota.elektrik_fiyatlari) AS ilk_fiyat_saati,
    (SELECT max(tarih_saat) FROM wattrota.elektrik_fiyatlari) AS son_fiyat_saati;
