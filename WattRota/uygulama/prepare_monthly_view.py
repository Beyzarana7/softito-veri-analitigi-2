"""Notebook 01 §4.4'teki mevcut aylık özetin sunum verisi (2024–2025)."""
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent / 'data/raw/epias'
rows=[]
for year in (2024,2025):
    path=next(SOURCE.glob(f'*0101{year}*.csv'))
    data=pd.read_csv(path,sep=';',dtype={'Tarih':str},decimal=',',thousands='.')
    month=pd.to_datetime(data.Tarih,format='%d.%m.%Y').dt.month
    summary=data.loc[month<=10].groupby(month[month<=10])['PTF (TL/MWh)'].agg(['mean','count']).reset_index()
    summary.columns=['ay','ortalama_ptf','saat_sayisi'];summary['yil']=year;rows.append(summary)
pd.concat(rows,ignore_index=True).to_csv(ROOT/'analysis_data/aylik_fiyat_profili.csv',index=False)
print('Mevcut aylık analiz için 20 özet satırı hazırlandı; 2026 okunmadı.')
