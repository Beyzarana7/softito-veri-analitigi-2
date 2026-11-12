"""Compact Turkish charts with a shared hour scale, independent of browser timezone."""
import altair as alt
import pandas as pd
from analytics import time_label,date_label,number

NAVY='#17344f';TEAL='#14766f';ORANGE='#c17d25';GRAY='#718397'
STATUS=['Üretim','Ürün değişimi','Yükleme','Bakım','Bekleme','Çalışma dışı']
STATUS_COLORS=[TEAL,'#7f9caf',NAVY,'#8a6c91','#dde5ec','#f2f5f8']
def with_hour(frame,start):
    f=frame.copy();f['saat_no']=(f.tarih_saat-pd.Timestamp(start))/pd.Timedelta(hours=1)
    return f
def axis(start,domain=(0,72)):
    labels=[time_label(pd.Timestamp(start)+pd.Timedelta(hours=h)).replace(' 2025','') for h in range(73)]
    # Quantitative positions keep Turkish local hours stable on every computer.
    expression=str(labels).replace("'",'"')+'[round(datum.value)]'
    ticks=[h for h in range(0,73,12) if domain[0]<=h<=domain[1]]
    return alt.X('saat_no:Q',title='Türkiye saati',scale=alt.Scale(domain=list(domain),nice=False),axis=alt.Axis(values=ticks,labelExpr=expression,labelAngle=0,labelFontSize=10,grid=False))
def style(chart):
    return chart.configure_view(stroke=None).configure_axis(labelColor='#526579',titleColor=NAVY,titleFontWeight='normal',labelFont='Segoe UI',titleFont='Segoe UI').configure_legend(title=None,labelFont='Segoe UI',orient='bottom')
def price_chart(prices,start,actual=False,height=220,domain=(0,72)):
    f=with_hour(prices,start);f['Saat']=f.tarih_saat.map(time_label)
    known=f[f.aciklanmis].copy();unknown=f[~f.aciklanmis].copy()
    known['Seri']='Açıklanmış';unknown['Seri']='Tahmin'
    pieces=[known,unknown]
    if actual and 'gercek_fiyat_tl_mwh' in f:
        real=f[~f.aciklanmis].copy();real['Seri']='Gerçekleşen';real.planlama_fiyati_tl_mwh=real.gercek_fiyat_tl_mwh;pieces.append(real)
    data=pd.concat(pieces,ignore_index=True);data['Fiyat']=data.planlama_fiyati_tl_mwh.map(number)
    series=['Açıklanmış','Tahmin']+(['Gerçekleşen'] if actual and 'gercek_fiyat_tl_mwh' in f else [])
    line=alt.Chart(data).mark_line(strokeWidth=2).encode(x=axis(start,domain),y=alt.Y('planlama_fiyati_tl_mwh:Q',title='PTF (TL/MWh)',axis=alt.Axis(format='.0f')),color=alt.Color('Seri:N',scale=alt.Scale(domain=series,range=[TEAL,ORANGE,NAVY][:len(series)])),strokeDash=alt.condition(alt.datum.Seri=='Tahmin',alt.value([6,3]),alt.value([1,0])),tooltip=['Saat:N',alt.Tooltip('Seri:N',title='Fiyat türü'),alt.Tooltip('Fiyat:N',title='TL/MWh')])
    result=line
    if len(unknown):
        boundary=pd.DataFrame({'saat_no':[unknown.saat_no.min()],'Etiket':['Tahmin başlangıcı']})
        rule=alt.Chart(boundary).mark_rule(color=GRAY,strokeDash=[3,3]).encode(x=axis(start,domain))
        text=alt.Chart(boundary).mark_text(align='left',dx=6,dy=7,baseline='top',fontSize=10,color=GRAY).encode(x=axis(start,domain),y=alt.value(0),text='Etiket:N')
        result=line+rule+text
    return result.properties(height=height)
def gantt_chart(gantt,start,machines,domain=(0,72),height=190):
    f=with_hour(gantt,start);f['saat_sonu']=f.saat_no+1
    f=f[f.Makine.isin(machines)&f.saat_no.ge(domain[0])&f.saat_no.lt(domain[1])]
    return alt.Chart(f).mark_bar(stroke='white',strokeWidth=.4).encode(x=axis(start,domain),x2='saat_sonu:Q',y=alt.Y('Makine:N',sort=machines,title=None,axis=alt.Axis(labelLimit=160)),color=alt.Color('Durum:N',scale=alt.Scale(domain=STATUS,range=STATUS_COLORS)),tooltip=['Makine:N','Saat:N','Durum:N','Ürün:N']).properties(height=height)
def linked_price_gantt(prices,gantt,start,machines,domain,actual):
    top=price_chart(prices,start,actual,height=175,domain=domain).properties(width=740)
    bottom=gantt_chart(gantt,start,machines,domain,height=max(100,30*len(machines))).properties(width=740)
    return style(alt.vconcat(top,bottom,spacing=14).resolve_scale(x='shared',color='independent'))
def cost_chart(reference,plan):
    f=pd.DataFrame({'Plan':['Referans','WattRota'],'Maliyet':[reference,plan]});f['Tutar']=f.Maliyet.map(lambda x:number(x)+' TL')
    f['BinTL']=f.Maliyet/1000
    return style(alt.Chart(f).mark_bar(size=32,cornerRadiusEnd=3).encode(x=alt.X('BinTL:Q',title='Gerçek fiyatlarla maliyet (bin TL)',axis=alt.Axis(format='.0f')),y=alt.Y('Plan:N',title=None,sort=['Referans','WattRota']),color=alt.Color('Plan:N',scale=alt.Scale(domain=['Referans','WattRota'],range=[GRAY,TEAL]),legend=None),tooltip=['Plan:N','Tutar:N']).properties(height=135))
def daily_chart(daily,actual):
    f=daily.melt(id_vars=['Gün','Tarih'],value_vars=['Referans','WattRota'],var_name='Plan',value_name='Maliyet');f['Tutar']=f.Maliyet.map(lambda x:number(x)+' TL')
    f['BinTL']=f.Maliyet/1000
    return style(alt.Chart(f).mark_bar().encode(x=alt.X('Tarih:N',sort=list(daily.Tarih),title=None,axis=alt.Axis(labelAngle=0)),xOffset=alt.XOffset('Plan:N',sort=['Referans','WattRota']),y=alt.Y('BinTL:Q',title=('Gerçekleşen' if actual else 'Beklenen')+' maliyet (bin TL)',axis=alt.Axis(format='.0f')),color=alt.Color('Plan:N',scale=alt.Scale(domain=['Referans','WattRota'],range=[GRAY,TEAL])),tooltip=['Tarih:N','Plan:N','Tutar:N']).properties(height=205))
def energy_chart(energy,start):
    f=with_hour(energy,start)
    # Always show the difference rather than hiding equal traces behind each other.
    f['Fark']=f.fark_kwh.map(lambda x:number(x,1)+' kWh')
    zero=f.fark_kwh.abs().max()<1e-7
    base=alt.Chart(f).mark_line(color=TEAL,strokeWidth=2) if zero else alt.Chart(f).mark_bar(color=TEAL,size=5)
    return style(base.encode(x=axis(start),y=alt.Y('fark_kwh:Q',title='WattRota − referans (kWh)',scale=alt.Scale(domain=[-1,1]) if zero else alt.Undefined,axis=alt.Axis(values=[-1,0,1],format='.0f') if zero else alt.Undefined),tooltip=['Saat:N','Fark:N']).properties(height=205))
