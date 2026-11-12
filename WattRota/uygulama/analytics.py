"""Presentation calculations from immutable saved plans; never runs a solver."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from service import load_inputs,evaluated_cost

MONTHS=['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık']
def number(value,digits=2):return f'{float(value):,.{digits}f}'.replace(',','X').replace('.',',').replace('X','.')
def money(value):return number(value)+' TL'
def date_label(value,year=False):
    t=pd.Timestamp(value)
    return f'{t.day} {MONTHS[t.month-1]}'+(f' {t.year}' if year else '')
def time_label(value):return date_label(value,True)+' '+pd.Timestamp(value).strftime('%H.%M')
def normalize(frame,columns):
    f=frame[columns].copy().fillna('')
    if 'tarih_saat' in f:f.tarih_saat=pd.to_datetime(f.tarih_saat)
    return f.sort_values(columns).reset_index(drop=True)
def compare_plans(plan,loads,reference,reference_loads):
    columns=['kaynak_id','tarih_saat','durum','urun_id','is_emri_id']
    left,right=normalize(plan,columns),normalize(reference,columns)
    production_same=left.equals(right)
    keys=['siparis_id','kaynak_id','tarih_saat']
    merged=loads.merge(reference_loads,on=keys,how='outer',suffixes=('_new','_ref')).fillna({'miktar_ton_new':0.,'miktar_ton_ref':0.})
    loading_same=bool(np.allclose(merged.miktar_ton_new,merged.miktar_ton_ref,atol=1e-6,rtol=0))
    changed=left.merge(right,on=['kaynak_id','tarih_saat'],how='outer',suffixes=('_new','_ref'))
    different=pd.Series(False,index=changed.index)
    for c in ['durum','urun_id','is_emri_id']:different|=changed[c+'_new'].fillna('').ne(changed[c+'_ref'].fillna(''))
    return {'production_identical':production_same,'loading_identical':loading_same,'identical':production_same and loading_same,'changed_resource_hours':int(different.sum()),'loading_absolute_difference_tonnes':float((merged.miktar_ton_new-merged.miktar_ton_ref).abs().sum())}
def gantt_rows(firm,plan,loads,index):
    names=firm['kaynaklar'].set_index('kaynak_id').kaynak_adi.to_dict()
    products=firm['urunler'].set_index('urun_id').urun_adi.to_dict()
    order_product=firm['siparisler'].set_index('siparis_id').urun_id.to_dict()
    grid=pd.MultiIndex.from_product([list(names),index],names=['kaynak_id','tarih_saat']).to_frame(index=False)
    grid=grid.merge(plan,on=['kaynak_id','tarih_saat'],how='left',validate='one_to_one')
    grid['durum']=grid.durum.fillna('kapali');grid['urun_id']=grid.urun_id.fillna('')
    load=loads.copy();load['urun_id_load']=load.siparis_id.map(order_product)
    grid=grid.merge(load[['kaynak_id','tarih_saat','miktar_ton','urun_id_load']],on=['kaynak_id','tarih_saat'],how='left',validate='one_to_one')
    active=grid.miktar_ton.fillna(0)>0;grid.loc[active,'durum']='yukleme';grid.loc[active,'urun_id']=grid.loc[active,'urun_id_load']
    grid=grid.merge(firm['kaynak_takvimi'],on=['kaynak_id','tarih_saat'],how='left',validate='one_to_one')
    grid.loc[grid.durum.eq('kapali')&grid.kullanilabilir.eq(False),'durum']='takvim_disi'
    for _,m in firm['bakimlar'].iterrows():
        mask=grid.kaynak_id.eq(m.kaynak_id)&grid.tarih_saat.ge(m.baslangic)&grid.tarih_saat.lt(m.bitis)
        # A maintenance overlay is valid only if actual activity is absent.
        if grid.loc[mask,'durum'].isin(['uretim','hazirlik','yukleme']).any():raise ValueError('Kaydedilmiş planda bakımla çakışan faaliyet var.')
        grid.loc[mask,'durum']='bakim'
    grid['Makine']=grid.kaynak_id.map(names)
    grid['Durum']=grid.durum.map({'uretim':'Üretim','hazirlik':'Ürün değişimi','kapali':'Bekleme','yukleme':'Yükleme','bakim':'Bakım','takvim_disi':'Çalışma dışı'})
    grid['Ürün']=grid.urun_id.map(products).fillna('—')
    grid['Saat']=grid.tarih_saat.map(time_label);grid['bitis']=grid.tarih_saat+pd.Timedelta(hours=1)
    return grid
def load_analysis(folder):
    folder=Path(folder);result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    d,e=result['decision'],result['evaluation'];firm=load_inputs(folder)
    plan=pd.read_csv(folder/'plan.csv',keep_default_na=False);plan.tarih_saat=pd.to_datetime(plan.tarih_saat)
    loads=pd.read_csv(folder/'loads.csv');loads.tarih_saat=pd.to_datetime(loads.tarih_saat)
    reference,ref_loads=firm['referans_plan'],firm['referans_yuklemeler']
    compare=compare_plans(plan,loads,reference,ref_loads)
    prices=pd.read_csv(folder/(e['price_file'] if e['status']=='Değerlendirildi' else 'prices.csv'))
    prices.tarih_saat=pd.to_datetime(prices.tarih_saat)
    index=pd.DatetimeIndex(prices.tarih_saat)
    use_actual=e['status']=='Değerlendirildi'
    col='gercek_fiyat_tl_mwh' if use_actual else 'planlama_fiyati_tl_mwh'
    series=prices.set_index('tarih_saat')[col]
    plan_cost,hourly=evaluated_cost(firm,plan,loads,series)
    reference_cost,ref_hourly=evaluated_cost(firm,reference,ref_loads,series)
    if use_actual:
        if abs(plan_cost-e['actual_cost_tl'])>.02 or abs(reference_cost-e['reference_actual_cost_tl'])>.02:raise ValueError('Kayıtlı maliyet ile grafik hesabı eşleşmiyor.')
    energy=hourly[['tarih_saat','toplam_enerji_kwh']].merge(ref_hourly[['tarih_saat','toplam_enerji_kwh']],on='tarih_saat',suffixes=('_plan','_ref'),validate='one_to_one')
    energy['fark_kwh']=energy.toplam_enerji_kwh_plan-energy.toplam_enerji_kwh_ref
    energy['Saat']=energy.tarih_saat.map(time_label)
    daily=hourly.assign(Gün=hourly.tarih_saat.dt.normalize()).groupby('Gün').karsilastirilan_maliyet_tl.sum().reset_index(name='WattRota')
    daily['Referans']=ref_hourly.assign(Gün=ref_hourly.tarih_saat.dt.normalize()).groupby('Gün').karsilastirilan_maliyet_tl.sum().to_numpy()
    daily['Tarih']=daily.Gün.map(date_label)
    orders=firm['siparisler'][['siparis_id','urun_id','miktar_ton','teslim_zamani']].merge(loads.groupby('siparis_id',as_index=False).miktar_ton.sum().rename(columns={'miktar_ton':'teslim_ton'}),on='siparis_id',how='left')
    orders['teslim_ton']=orders.teslim_ton.fillna(0);orders['karşılama_pct']=100*orders.teslim_ton/orders.miktar_ton
    products=firm['urunler'].set_index('urun_id').urun_adi.to_dict();orders['Ürün']=orders.urun_id.map(products)
    gantt=gantt_rows(firm,plan,loads,index);ref_gantt=gantt_rows(firm,reference,ref_loads,index)
    availability=firm['kaynak_takvimi'].groupby('kaynak_id').kullanilabilir.sum()
    active=gantt[gantt.durum.isin(['uretim','hazirlik','yukleme'])].groupby('kaynak_id').size()
    utilization=pd.DataFrame({'Uygun saat':availability,'Aktif saat':active}).fillna(0).reset_index()
    utilization['Makine']=utilization.kaynak_id.map(firm['kaynaklar'].set_index('kaynak_id').kaynak_adi)
    utilization['Kullanım (%)']=100*utilization['Aktif saat']/utilization['Uygun saat']
    forecast=prices[~prices.aciklanmis]
    mae=float((forecast.planlama_fiyati_tl_mwh-forecast.gercek_fiyat_tl_mwh).abs().mean()) if use_actual and len(forecast) else None
    return dict(folder=folder,result=result,decision=d,evaluation=e,firm=firm,prices=prices,plan=plan,loads=loads,comparison=compare,energy=energy,daily=daily,orders=orders,gantt=gantt,reference_gantt=ref_gantt,utilization=utilization,mae=mae,use_actual=use_actual,hourly=hourly,reference_hourly=ref_hourly)
