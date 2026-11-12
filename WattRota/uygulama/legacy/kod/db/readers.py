"""SQL tablolarını mevcut firma/fiyat yükleyicilerinin veri yapılarına dönüştürür."""
import numpy as np
import pandas as pd
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, MetaData, String, Table, select

from .engine import db_transaction

FIRM_TABLES = ('urunler','kaynaklar','kaynak_urun','isletme_kurallari','urun_gecisleri',
               'stok_alanlari','depo_kurallari','rotalar','siparisler','is_emirleri',
               'is_emri_siparis_baglantisi','kaynak_takvimi','bakimlar','tesis_takvimi',
               'fiyatlar','rota_kaynaklari','referans_plan','referans_yuklemeler')
BASE_TABLES = FIRM_TABLES + ('rota_tanimlari','elektrik_fiyatlari')


def read_table(conn, name):
    if name not in BASE_TABLES:
        raise ValueError('Bu tablo firma okuma katmanında tanımlı değil.')
    catalog=MetaData()
    table = Table(name, catalog, schema='wattrota', autoload_with=conn)
    order = list(table.primary_key.columns)
    if not order:
        raise ValueError('Belirli okuma sırası için birincil anahtar gerekli.')
    query=select(table).order_by(*order)
    if name=='referans_yuklemeler':
        # Referans CSV: teslim penceresi günü, yükleme kaynağı, ürün ve saat sırası.
        orders=Table('siparisler',catalog,schema='wattrota',autoload_with=conn)
        query=select(table).select_from(table.join(orders,table.c.siparis_id==orders.c.siparis_id)).order_by(
            orders.c.en_erken_yukleme,table.c.kaynak_id,orders.c.urun_id,table.c.tarih_saat,table.c.siparis_id)
    frame = pd.read_sql(query, conn)
    for column in table.columns:
        field, kind = column.name, column.type
        if isinstance(kind, DateTime):
            frame[field] = pd.to_datetime(frame[field]).astype('datetime64[us]')
        elif isinstance(kind, Boolean):
            frame[field] = frame[field].astype('bool')
        elif isinstance(kind, (Integer, BigInteger)):
            frame[field] = frame[field].astype('int64')
        elif isinstance(kind, Float):
            frame[field] = frame[field].astype('float64')
        elif isinstance(kind, String):
            # Kapalı referans satırlarının SQL NULL değerleri, CSV'deki boş alanla eşleşir.
            frame[field] = frame[field].fillna('').astype('str')
    return frame.reset_index(drop=True)


def read_firm(engine):
    with db_transaction(engine) as conn:
        return {name:read_table(conn,name) for name in FIRM_TABLES}


def read_prices(engine):
    with db_transaction(engine) as conn:
        frame=read_table(conn,'elektrik_fiyatlari')
    series=frame.set_index('tarih_saat')['PTF (TL/MWh)'].astype(float)
    if series.empty or series.index.has_duplicates or not series.index.equals(pd.date_range(series.index.min(),series.index.max(),freq='h')):
        raise ValueError('Fiyat serisi boş, eksik veya tekrarlı.')
    if not np.isfinite(series).all() or (series<0).any():
        raise ValueError('Fiyatlar sonlu ve negatif olmayan değerler olmalı.')
    return series
