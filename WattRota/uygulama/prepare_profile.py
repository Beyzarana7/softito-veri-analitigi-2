"""Mevcut 2024–2025 EDA verilerinin saat profili; model/deney çalıştırmaz."""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent / 'data/raw/epias'
rows=[];sources=[]
for year in (2024,2025):
    p=next(SOURCE.glob(f'*0101{year}*.csv'))
    f=pd.read_csv(p,sep=';',dtype={'Tarih':str},decimal=',',thousands='.')
    t=pd.to_datetime(f.Tarih+' '+f.Saat,format='%d.%m.%Y %H:%M')
    profile=f.groupby(t.dt.hour)['PTF (TL/MWh)'].agg(['mean','count']).reset_index()
    profile.columns=['saat','ortalama_ptf','saat_sayisi'];profile['yil']=year;rows.append(profile)
    sources.append({'dosya':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'satir':len(f),'ilk':str(t.min()),'son':str(t.max())})
dest=ROOT/'analysis_data';dest.mkdir(exist_ok=True)
pd.concat(rows,ignore_index=True).to_csv(dest/'saatlik_fiyat_profili.csv',index=False)
(dest/'kaynak.json').write_text(json.dumps({'kaynak':'EPİAŞ, mevcut proje CSV verileri','kapsam':'2024 ve 2025 tam yılları; 2026 ve kilitli test haftaları dahil edilmedi','dosyalar':sources},ensure_ascii=False,indent=2),encoding='utf-8')
print('Mevcut EDA saat profili:',sum(x['satir'] for x in sources),'saat, 48 özet satırı')
