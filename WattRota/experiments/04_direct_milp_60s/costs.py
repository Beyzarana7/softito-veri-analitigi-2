"""Doğrulayıcı maliyetini çakışmayan elektrik ve olay giderlerine ayırır."""
import numpy as np
import pandas as pd

ADDITIVE=['operating_electricity_tl','startup_electricity_tl','transition_electricity_tl',
          'startup_non_electric_tl','transition_non_electric_tl','plan_change_tl']


def cost_breakdown(firm,validated):
    _,activity,hourly,_=validated
    result=hourly[['tarih_saat']].copy().set_index('tarih_saat')
    for column in ADDITIVE:result[column]=0.
    rules=firm['isletme_kurallari'].set_index('kaynak_id')
    transitions=firm['urun_gecisleri'].set_index(['kaynak_id','onceki_urun','sonraki_urun'])
    prices=hourly.set_index('tarih_saat')['PTF (TL/MWh)']
    for resource,rows in activity.groupby('kaynak_id'):
        rule=rules.loc[resource];setting=rule['baslangic_urun_ayari']
        previous_state='kapali';previous_product=''
        for row in rows.sort_values('tarih_saat').itertuples(index=False):
            if previous_state=='hazirlik' and (row.durum!='hazirlik' or row.urun_id!=previous_product):
                setting=previous_product
            start_energy=float(rule['baslatma_enerjisi_kwh'])*row.baslatma
            result.loc[row.tarih_saat,'startup_electricity_tl']+=start_energy*prices.loc[row.tarih_saat]/1000
            result.loc[row.tarih_saat,'startup_non_electric_tl']+=row.baslatma*float(rule['baslatma_elektrik_disi_gider_tl'])
            if row.durum=='hazirlik':
                result.loc[row.tarih_saat,'transition_electricity_tl']+=(row.enerji_kwh-start_energy)*prices.loc[row.tarih_saat]/1000
                if previous_state!='hazirlik' or previous_product!=row.urun_id:
                    result.loc[row.tarih_saat,'transition_non_electric_tl']+=float(transitions.loc[(resource,setting,row.urun_id),'elektrik_disi_gider_tl'])
            previous_state,previous_product=row.durum,row.urun_id
    h=hourly.set_index('tarih_saat')
    result['operating_electricity_tl']=h['ptf_bedeli_tl']-result['startup_electricity_tl']-result['transition_electricity_tl']
    result['plan_change_tl']=h['degisiklik_gideri_tl']
    result['total_electricity_tl']=h['ptf_bedeli_tl']
    result['total_cost_tl']=result[ADDITIVE].sum(axis=1)
    np.testing.assert_allclose(result['startup_non_electric_tl']+result['transition_non_electric_tl'],h['elektrik_disi_gider_tl'],atol=1e-7,rtol=0)
    np.testing.assert_allclose(result['total_cost_tl'],h['karsilastirilan_maliyet_tl'],atol=1e-7,rtol=0)
    return result.reset_index()
