"""ML katkı oranını geçmiş yılın karar maliyetiyle seçen basit birleşim."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from fiyat_tahmini import elektrik_fiyatlarini_oku

ORANLAR=[0.0,0.25,0.5,0.75,1.0]


def karar_odakli_kalibrasyon(proje,tahmin_dizini,havuz_dizini):
    proje=Path(proje);folder=Path(tahmin_dizini);havuz=Path(havuz_dizini)
    t=pd.read_csv(folder/'saatlik_tahminler.csv',parse_dates=['karar_zamani','tarih_saat'])
    secilen=json.loads((folder/'secilen_model.json').read_text(encoding='utf-8'))['model']
    fiyat=elektrik_fiyatlarini_oku(proje)
    e=np.load(havuz/'saatlik_enerji.npy');idx=pd.read_csv(havuz/'plan_indeksi.csv')
    gider=idx['elektrik_disi_gider_tl'].to_numpy()
    def fiyatlar(karar):
        d=t[t['karar_zamani']==karar]
        b=d[d['model']=='son_yayinlanan_gun'].sort_values('tarih_saat')['tahmin'].to_numpy()
        m=d[d['model']==secilen].sort_values('tarih_saat')['tahmin'].to_numpy()
        if len(b)!=48 or len(m)!=48:raise ValueError('Birleşim için tahminler eksik.')
        gercek=fiyat.reindex(pd.date_range(karar,periods=72,freq='h')).to_numpy()
        return b,m,gercek
    kayitlar=[]
    for karar in sorted(t.loc[t['karar_zamani']<pd.Timestamp('2026-01-01'),'karar_zamani'].unique()):
        b,m,g=fiyatlar(karar);gercek_maliyet=e@g/1000+gider
        for oran in ORANLAR:
            kullanilan=np.r_[g[:24],(1-oran)*b+oran*m]
            sec=int(np.argmin(e@kullanilan/1000+gider))
            kayitlar.append([pd.Timestamp(karar),oran,gercek_maliyet[sec],gercek_maliyet[sec]-gercek_maliyet.min()])
    val=pd.DataFrame(kayitlar,columns=['karar_zamani','ml_orani','gercek_maliyet_tl','havuz_minimumuna_fark_tl'])
    ozet=val.groupby('ml_orani',as_index=False)['gercek_maliyet_tl'].mean().sort_values(['gercek_maliyet_tl','ml_orani'])
    oran=float(ozet.iloc[0]['ml_orani'])
    # 2026 birleşim sonuçları hesaplanmadan oran kilitlenir; eşitlikte daha az ML.
    (folder/'karar_kalibrasyonu.json').write_text(json.dumps(dict(ml_model=secilen,ml_orani=oran,
        aday_oranlar=ORANLAR,secim_donemi='2025 tamamı',olcut='Ortak planlarda ortalama gerçekleşmiş maliyet',
        yorum='2025 bu oran için kalibrasyon dönemidir; 2026 daha önce görülmüş geriye dönük karşılaştırmadır.'),ensure_ascii=False,indent=2),encoding='utf-8')
    val.to_csv(folder/'karar_kalibrasyon_kayitlari.csv',index=False,encoding='utf-8-sig')
    ozet.to_csv(folder/'karar_kalibrasyon_ozeti.csv',index=False,encoding='utf-8-sig')
    yeni=[]
    for karar in sorted(t.loc[t['karar_zamani']>=pd.Timestamp('2026-01-01'),'karar_zamani'].unique()):
        b,m,g=fiyatlar(karar)
        for saat,p,gercek in zip(pd.date_range(karar+pd.Timedelta(hours=24),periods=48,freq='h'),(1-oran)*b+oran*m,g[24:]):
            yeni.append(['geriye_donuk_2026','karar_odakli_birlesim',karar,saat,2 if saat<karar+pd.Timedelta(hours=48) else 3,gercek,p])
    pd.DataFrame(yeni,columns=t.columns).to_csv(folder/'birlesim_tahminleri.csv',index=False,encoding='utf-8-sig')
    print('2025 karar maliyetiyle seçilen ML oranı:',oran,flush=True)
    print(ozet.to_string(index=False),flush=True)


if __name__=='__main__':
    import sys
    karar_odakli_kalibrasyon(*sys.argv[1:4])
