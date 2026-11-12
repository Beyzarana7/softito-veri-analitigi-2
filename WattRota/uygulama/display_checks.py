"""İki ekranın sunum hesapları; fiyat tahmini veya optimizasyon yapmaz."""
import numpy as np
import pandas as pd

COST_COLUMNS=['Beklenen maliyet (TL)','Gerçekleşen maliyet (TL)','Referans gerçek maliyeti (TL)','Avantaj (TL)']

def daily_cost_table(daily):
    view=daily[['Tarih']+COST_COLUMNS].copy()
    total={'Tarih':'72 Saatlik Toplam'}
    for column in COST_COLUMNS:
        values=pd.to_numeric(view[column],errors='raise')
        # Bir günün gerçekleşeni eksikse 72 saatlik gerçekleşen toplamı da bilinmiyor.
        total[column]=values.sum(min_count=len(values)) if len(values) else np.nan
    return pd.concat([view,pd.DataFrame([total])],ignore_index=True)

def schedule_differences(a,machines,start,end):
    fields=['kaynak_id','tarih_saat','Makine','Saat','Durum','Ürün','is_emri_id','miktar_ton']
    left=a['gantt'][fields].copy();right=a['reference_gantt'][fields].copy()
    joined=left.merge(right,on=['kaynak_id','tarih_saat'],suffixes=('','_ref'),validate='one_to_one')
    different=pd.Series(False,index=joined.index)
    for c in ('Durum','Ürün','is_emri_id'):
        different|=joined[c].fillna('').ne(joined[c+'_ref'].fillna(''))
    different|=(joined.miktar_ton.fillna(0)-joined.miktar_ton_ref.fillna(0)).abs()>1e-6
    joined=joined[different & joined.Makine.isin(machines) & joined.tarih_saat.ge(start) & joined.tarih_saat.lt(end)].copy()
    records=[]
    for _,row in joined.iterrows():
        for label,suffix in [('Referans Plan','_ref'),('WattRota Planı','')]:
            records.append({'kaynak_id':row.kaynak_id,'tarih_saat':row.tarih_saat,'Makine':row.Makine,
                'Plan':label,'Satır':row.Makine+' · '+label,'Saat':row.Saat,'Durum':row['Durum'+suffix],
                'Ürün':row['Ürün'+suffix],'İş emri':row['is_emri_id'+suffix] if pd.notna(row['is_emri_id'+suffix]) and row['is_emri_id'+suffix]!='' else '—',
                'Yükleme (ton)':float(row['miktar_ton'+suffix]) if pd.notna(row['miktar_ton'+suffix]) else 0.})
    chart=pd.DataFrame(records)
    table=joined[['Makine','Saat','Durum_ref','Durum','Ürün_ref','Ürün','is_emri_id_ref','is_emri_id','miktar_ton_ref','miktar_ton']].rename(columns={
        'Durum_ref':'Referans durumu','Durum':'WattRota durumu','Ürün_ref':'Referans ürünü','Ürün':'WattRota ürünü',
        'is_emri_id_ref':'Referans iş emri','is_emri_id':'WattRota iş emri','miktar_ton_ref':'Referans yükleme (ton)','miktar_ton':'WattRota yükleme (ton)'})
    for c in ('Referans yükleme (ton)','WattRota yükleme (ton)'):table[c]=table[c].fillna(0)
    return table,chart
