"""Yalnız sunum yardımcıları. Optimizasyon veya yeni deney çalıştırmaz."""
import pandas as pd
from display_checks import schedule_differences

def clean_change_table(changes):
    result=changes.rename(columns=lambda c:c.replace('Referans','Mevcut').replace('WattRota','Önerilen')).copy()
    for col in result:
        if not pd.api.types.is_numeric_dtype(result[col]):result[col]=result[col].fillna('—').replace({'':'—','None':'—','NaN':'—','nan':'—','<NA>':'—'})
    return result

def change_summary(a):
    names=a['firm']['kaynaklar'].kaynak_adi.tolist();times=a['gantt'].tarih_saat
    changes,_=schedule_differences(a,names,times.min(),times.max()+pd.Timedelta(hours=1))
    counts=changes.groupby('Makine').size().reindex(names,fill_value=0)
    active=a['engineering']['machines'].pivot(index='Makine',columns='Plan',values='Aktif (saat)').reindex(names)
    result=pd.DataFrame({'Makine':names,'Mevcut aktif (saat)':active['Referans'].to_numpy(),
        'Önerilen aktif (saat)':active['WattRota'].to_numpy(),'Değişen saat kaydı':counts.to_numpy()})
    return result,changes
