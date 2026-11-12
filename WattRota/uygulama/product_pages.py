"""Ürün sayfaları; grafikler yalnız seçilmiş gerçek kayıtlardan üretilir."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from analytics import load_analysis,number,money,time_label,date_label
from charts import style,price_chart,gantt_chart,linked_price_gantt,energy_chart,axis,with_hour,TEAL,NAVY,GRAY,STATUS,STATUS_COLORS
from engineering import engineering
from planning_page import render_ready
from input_page import render as render_input
from display_checks import daily_cost_table,schedule_differences

PAGES=['Kontrol Paneli','Üretim Planlama','Üretim Çizelgesi','Enerji ve Maliyet','Plan Geçmişi']
TITLE='Elektrik Fiyat Tahminine Dayalı Üretim Çizelgeleme Platformu'
NUMBER_LABEL="replace(format(datum.value, ',.0f'), /,/g, '.')"

@st.cache_data(show_spinner=False)
def analysis(folder):
    a=load_analysis(folder);a['engineering']=engineering(a);return a

def formatted(frame):
    frame=frame.copy()
    for c in frame:
        if pd.api.types.is_numeric_dtype(frame[c]) or 'TL)' in c:frame[c]=frame[c].map(lambda v:'Henüz değerlendirilemedi' if pd.isna(v) else number(v,1 if '%' in c else 2 if 'TL' in c else 0))
    return frame

def bars(frame,category,value,unit,height=210):
    data=frame.copy();data['Değer']=data[value].map(lambda v:number(v,1)+' '+unit)
    return style(alt.Chart(data).mark_bar(cornerRadiusEnd=2).encode(
        y=alt.Y(category+':N',title=None,axis=alt.Axis(labelLimit=180)),
        x=alt.X(value+':Q',title=unit,axis=alt.Axis(labelExpr=NUMBER_LABEL)),yOffset='Plan:N',
        color=alt.Color('Plan:N',scale=alt.Scale(domain=['Referans','WattRota'],range=[GRAY,TEAL])),
        tooltip=[category+':N','Plan:N','Değer:N']).properties(height=height))

def history(root):
    records=[];errors=[]
    for file in sorted((root/'runs').glob('*/result.json'),reverse=True):
        try:
            r=json.loads(file.read_text(encoding='utf-8'));d,e=r['decision'],r['evaluation']
            records.append({'folder':str(file.parent),'Dönem':date_label(d['plan_start'],True)+' – '+date_label(pd.Timestamp(d['plan_end_exclusive'])-pd.Timedelta(hours=1),True),
                'Oluşturulma':time_label(d['created_at']),'Durum':'Doğrulandı' if d.get('independent_validation') else 'Doğrulanmadı',
                'Beklenen (TL)':d['expected_cost_tl'],'Gerçekleşen (TL)':e.get('actual_cost_tl'),
                'Avantaj (TL)':e.get('actual_advantage_tl'),'raw':r})
        except (ValueError,KeyError,TypeError) as exc:errors.append(file.parent.name+': '+type(exc).__name__)
    return records,errors

def render(root,metrics,plot,caption,table,no_plan,solution_note,equality_note):
    st.markdown('''<style>
    .block-container{max-width:1450px;padding-top:1.5rem}.wr-brand{font-size:2rem;font-weight:750;letter-spacing:-.06em;margin:0;color:white}.wr-tag{font-size:.78rem;line-height:1.45;color:#bed4df;margin:4px 0 24px}
    [data-testid="stMetric"]{min-height:95px;padding:12px 14px}[data-testid="stMetricValue"]{font-size:1.3rem!important}
    [data-testid="stSidebar"]{min-width:250px;max-width:270px}h1{font-size:1.6rem!important}
    </style>''',unsafe_allow_html=True)
    st.sidebar.markdown('<div class="wr-brand">WattRota</div><div class="wr-tag">'+TITLE+'</div>',unsafe_allow_html=True)
    if st.session_state.get('nav') not in PAGES:st.session_state.nav=PAGES[0]
    page=st.sidebar.radio('Çalışma alanı',PAGES,key='nav',label_visibility='collapsed')
    st.sidebar.caption('Örnek çimento fabrikası')
    st.title(page);st.caption(TITLE)
    a=None;folder=st.session_state.get('run_folder')
    if folder:
        try:a=analysis(folder)
        except Exception as exc:st.error('Kayıt analiz edilemedi: '+str(exc))
    if a:
        d,e=a['decision'],a['evaluation'];eng=a['engineering'];start=pd.Timestamp(d['plan_start'])
        st.caption(st.session_state.get('plan_origin','Seçili kayıt')+' · '+date_label(start,True)+' – '+date_label(start+pd.Timedelta(days=2),True))
    if page==PAGES[0]:
        st.write('Elektrik fiyatlarını ve üretim koşullarını birlikte değerlendirerek makinelerin çalışma zamanlarını planlayın.')
        if not a:
            no_plan()
            metrics([('Seçili fabrika','Örnek çimento fabrikası'),('Planlama durumu','Plan bekleniyor'),('Sonraki işlem','Üretim planlama')])
        else:
            metrics([('Üretim miktarı',number(eng['produced_tonnes'],0)+' ton'),('Karşılanan sipariş',str(int((a['orders']['karşılama_pct']>=99.999).sum()))+' / '+str(len(a['orders']))),('Gerçekleşen avantaj',money(e['actual_advantage_tl']) if a['use_actual'] else 'Henüz değerlendirilemedi')])
            left,right=st.columns([1.1,1])
            with left,st.container(border=True):
                st.subheader('Planın durumu')
                table(pd.DataFrame({'Bilgi':['Fabrika','Dönem','Kısıt uygunluğu','Sonraki işlem'],'Değer':['Örnek çimento fabrikası',date_label(start,True)+' – '+date_label(start+pd.Timedelta(days=2),True),'Bağımsız doğrulama geçti' if d['independent_validation'] else 'Doğrulanmadı','Üretim Çizelgesi ve Enerji ve Maliyet bölümlerini inceleyin']}))
                st.button('Üretim Planlamaya Git',on_click=lambda:setattr(st.session_state,'nav',PAGES[1]))
            with right,st.container(border=True):
                st.subheader('Günlük üretim ve teslim')
                table(formatted(eng['performance'][['Tarih','WattRota üretim (ton)','Teslim (ton)','Tamamlanan sipariş']].rename(columns={'WattRota üretim (ton)':'Üretim (ton)','Tamamlanan sipariş':'Sipariş'})))
                caption('Üretim öğütme çıktısıdır; paketleme aynı tonları tekrar üretim sayısına eklemez. Teslim ayrı bir akıştır.')
            solution_note(a)
    elif page==PAGES[1]:
        mode=st.radio('Planlama çalışma alanı',['Hazır fabrika','Kendi Planını Oluştur'],horizontal=True,key='planning_mode')
        if mode=='Hazır fabrika':
            render_ready(root,a,metrics,caption,plot,solution_note)
            with st.expander('Yöntem ve kapsam'):
                st.write('Mevcut MILP modeli, fiyat tahmini ve yerel ön iyileştirme kullanılır. Karar anında yalnız açıklanmış fiyatlar bilinir; geçmiş yayın bilgisi önceki gün 14.00 varsayımına dayanır. Canlı EPİAŞ bağlantısı değildir. Süre sınırı kesin optimum garantisi vermez. Bedeller tam elektrik faturası değildir.')
        else:render_input()
    elif page==PAGES[2]:
        if not a:no_plan();return
        equality_note(a)
        cols=st.columns([3,1]);machines=list(a['firm']['kaynaklar'].kaynak_adi)
        selected=cols[0].multiselect('Makineler',machines,default=machines)
        days=[date_label(start+pd.Timedelta(days=i)) for i in range(3)]
        day=cols[1].selectbox('Gün',['Üç gün']+days)
        which=st.radio('Plan görünümü',['Referans Plan','WattRota Planı','Değişiklikleri Göster'],index=1,horizontal=True)
        domain=(0,72) if day=='Üç gün' else (24*days.index(day),24*(days.index(day)+1))
        if not selected:st.info('En az bir makine seçin.');return
        st.subheader('Makine çalışma çizelgesi')
        changes,diff_grid=schedule_differences(a,selected,start+pd.Timedelta(hours=domain[0]),start+pd.Timedelta(hours=domain[1]))
        legend=alt.Legend(columns=3,labelLimit=160)
        if which=='Değişiklikleri Göster':
            if changes.empty:
                st.info('Seçili makine ve günlerde üretim, iş emri ve yükleme kararları referansla aynı.')
            else:
                f=with_hour(diff_grid,start);f['saat_sonu']=f.saat_no+1
                ordered=[name+' · '+label for name in selected if name in set(f.Makine) for label in ('Referans Plan','WattRota Planı')]
                chart=alt.Chart(f).mark_bar(stroke='white',strokeWidth=.5).encode(x=axis(start,domain),x2='saat_sonu:Q',
                    y=alt.Y('Satır:N',title=None,sort=ordered,axis=alt.Axis(labelLimit=270,labelFontSize=12,labelPadding=8)),
                    color=alt.Color('Durum:N',scale=alt.Scale(domain=STATUS,range=STATUS_COLORS),legend=legend),
                    tooltip=['Makine:N','Plan:N','Saat:N','Durum:N','Ürün:N','İş emri:N','Yükleme (ton):Q']).properties(height=max(290,35*len(ordered)+110))
                plot(style(chart));caption(str(len(changes))+' farklı makine-saati gösteriliyor. Her makinenin iki satırı aynı saatlerde karşılaştırılır; değişmeyen saatler boş bırakılır. Yükleme miktarı farklı olup durum rengi aynı kalan saatler de dahildir.')
        else:
            grid=a['gantt'] if which=='WattRota Planı' else a['reference_gantt']
            chart=gantt_chart(grid,start,selected,domain,height=max(270,35*len(selected)+110))
            chart=chart.encode(y=alt.Y('Makine:N',title=None,sort=selected,axis=alt.Axis(labelLimit=230,labelFontSize=12,labelPadding=8)),
                color=alt.Color('Durum:N',scale=alt.Scale(domain=STATUS,range=STATUS_COLORS),legend=legend))
            plot(style(chart))
        caption('Bakım tablodaki gerçek bakım aralıklarını, bekleme ise takvimde uygun olup çalışılmayan saatleri gösterir. Ürün değişimi aktif süreye dahildir.')
        stats=eng['machines'][eng['machines'].Makine.isin(selected)]
        # Özetler seçilen günle aynı aralık için yeniden sayılır; enerji ayrı 72 saatlik bölümde kalır.
        if day!='Üç gün':
            rows=[]
            for label,grid in [('Referans',a['reference_gantt']),('WattRota',a['gantt'])]:
                sub=grid[(grid.tarih_saat>=start+pd.Timedelta(hours=domain[0]))&(grid.tarih_saat<start+pd.Timedelta(hours=domain[1]))&grid.Makine.isin(selected)]
                for name,g in sub.groupby('Makine'):
                    ct=g.durum.value_counts();active=g.durum.isin(['uretim','hazirlik','yukleme']).sum();available=g.kullanilabilir.sum()
                    rows.append({'Makine':name,'Plan':label,'Üretim (saat)':ct.get('uretim',0),'Yükleme (saat)':ct.get('yukleme',0),'Ürün değişimi (saat)':ct.get('hazirlik',0),'Aktif (saat)':active,'Bekleme (saat)':ct.get('kapali',0),'Bakım (saat)':ct.get('bakim',0),'Çalışma dışı (saat)':ct.get('takvim_disi',0),'Uygun (saat)':available,'Kullanım (%)':100*active/available if available else np.nan})
            stats=pd.DataFrame(rows)
        l,r=st.columns(2)
        with l:
            st.subheader('Makine kullanım oranları');plot(bars(stats,'Makine','Kullanım (%)','%',230));caption('Aktif saat / takvimde uygun saat. Bu oran ton/saat kapasite doluluğu değildir.')
        with r:
            st.subheader('Aktif çalışma süreleri');plot(bars(stats,'Makine','Aktif (saat)','saat',230));caption('Üretim, ürün değişimi ve yükleme saatleri birlikte sayılır. Bakım ve çalışma dışı saatler aktif değildir.')
        table(formatted(stats[['Makine','Plan','Aktif (saat)','Bekleme (saat)','Bakım (saat)','Ürün değişimi (saat)','Kullanım (%)']].rename(columns={'Ürün değişimi (saat)':'Geçiş (saat)'})))
        with st.expander('Üretim, yükleme ve takvim sürelerinin tamamı'):table(formatted(stats))
        st.subheader('Değişen çalışma ve yükleme zamanları')
        if changes.empty:st.info('Seçili aralıkta durum, ürün veya yükleme miktarı değişmedi.')
        else:table(formatted(changes.fillna({'Referans yükleme (ton)':0,'WattRota yükleme (ton)':0})))
        caption('Saat bazındaki farklılıklar gösterilir. Aynı toplam çalışma süresi, aynı saatlerde çalışıldığı anlamına gelmez.')
        with st.expander('Çizelgeyi indir ve doğrulama ayrıntıları'):
            st.download_button('Çizelgeyi CSV indir',(Path(folder)/'plan.csv').read_bytes(),file_name='WattRota_Uretim_Plani.csv');solution_note(a)
    elif page==PAGES[3]:
        if not a:no_plan();return
        cost,energy,forecast=st.tabs(['Günlük maliyet','Enerji ve üretim','Tahmin ve gerçekleşen'])
        with cost:
            metrics([('Beklenen plan maliyeti',money(d['expected_cost_tl'])),('Gerçekleşen plan maliyeti',money(e['actual_cost_tl']) if a['use_actual'] else 'Henüz değerlendirilemedi'),('Gerçekleşen avantaj',money(e['actual_advantage_tl']) if a['use_actual'] else 'Henüz değerlendirilemedi')])
            daily=eng['daily'];table(formatted(daily_cost_table(daily)))
            if a['use_actual']:
                data=daily.melt(id_vars=['Tarih'],value_vars=['Gerçekleşen maliyet (TL)','Referans gerçek maliyeti (TL)'],var_name='Plan',value_name='Maliyet')
                data['Plan']=data.Plan.map({'Gerçekleşen maliyet (TL)':'WattRota','Referans gerçek maliyeti (TL)':'Referans'})
                plot(bars(data,'Tarih','Maliyet','TL',210))
                best=daily.loc[daily['Avantaj (TL)'].idxmax()];caption('En yüksek günlük avantaj '+best.Tarih+': '+money(best['Avantaj (TL)'])+'. Üç günün toplamı '+money(daily['Avantaj (TL)'].sum())+'. Negatif değer ek maliyettir.')
            else:st.info('Gerçek fiyatlar tamamlanmadan gerçekleşen maliyet ve avantaj hesaplanmaz.')
            caption('Günlük toplamlar kayıtlı 72 saatlik maliyetlerle kontrol edilir. Tahmin sapması tasarruf değildir. Başlatma ve ürün geçişi giderleri modellenen toplam maliyete dahildir.')
        with energy:
            en=a['energy'];same=abs(en.fark_kwh.sum())<1e-6
            metrics([('WattRota enerjisi',number(en.toplam_enerji_kwh_plan.sum(),0)+' kWh'),('Referans enerjisi',number(en.toplam_enerji_kwh_ref.sum(),0)+' kWh'),('Enerji farkı',number(en.fark_kwh.sum(),0)+' kWh')])
            if same:st.info('İki planın toplam enerji tüketimi aynı. Maliyet değişimi, zamanlama ve olay giderleriyle ayrıca değerlendirilir.')
            l,r=st.columns(2)
            with l:
                st.subheader('Makine bazında enerji');plot(bars(eng['machine_energy'],'Makine','Enerji (kWh)','kWh',230));caption('Başlatma ve ürün değişimi enerjisi üretim kaynağına dahildir. Tesis temel yükü ayrı: '+number(eng['base_energy'],0)+' kWh. Makine toplamları ve temel yük, tesis tüketimiyle eşleşir.')
            with r:
                st.subheader('Fiyata göre üretim dağılımı');plot(bars(eng['distribution'],'Fiyat grubu','Üretim (ton)','ton',230));caption('Düşük fiyat: planlamada kullanılan 72 saatin medyanına eşit veya altında ('+number(eng['median_price'])+' TL/MWh). Yalnız öğütme çıktısı sayılır; bu dağılım tek başına neden-sonuç kanıtı değildir.')
            st.subheader('Saatlik tesis tüketimi')
            f=with_hour(en,start);f['Tüketim']=f.toplam_enerji_kwh_plan.map(lambda x:number(x,0)+' kWh')
            plot(style(alt.Chart(f).mark_area(color=TEAL,opacity=.28,line=True).encode(x=axis(start),y=alt.Y('toplam_enerji_kwh_plan:Q',title='Enerji (kWh)',axis=alt.Axis(labelExpr=NUMBER_LABEL)),tooltip=['Saat:N','Tüketim:N']).properties(height=175)))
            caption('WattRota planının saatlik toplamı üretim, yükleme, başlatma ve tesis temel yükünü kapsar.')
            if en.fark_kwh.abs().max()>1e-6:
                plot(energy_chart(en,start));caption('Pozitif fark o saatte WattRota tüketiminin referanstan yüksek olduğunu gösterir.')
            else:st.info('Saatlik tüketimler de aynı; sıfır fark grafiği gösterilmedi.')
            st.subheader('Günlük üretim ve teslim performansı');table(formatted(eng['performance'].drop(columns='Gün')));caption('Üretim ve teslim farklı stok akışlarıdır. Sipariş sayısı son yükleme gününe göre gösterilir; yalnız doğrulanmış tam teslimler kullanılır.')
        with forecast:
            plot(style(price_chart(a['prices'],start,a['use_actual'],height=230)))
            caption(str(d['announced_hours'])+' saat açıklanmış, '+str(d['forecast_hours'])+' saat tahmin. Sonradan açıklanan fiyatlar karar oluşturma girdisine eklenmez.')
            metrics([('Beklenen maliyet',money(d['expected_cost_tl'])),('Gerçek − beklenen fark',money(e['forecast_cost_difference_tl']) if a['use_actual'] else 'Henüz değerlendirilemedi'),('Fiyat tahmin hatası',number(a['mae'])+' TL/MWh' if a['mae'] is not None else 'Henüz değerlendirilemedi')])
            caption('Hata yalnız karar anında bilinmeyen saatlerde ölçülür. Gerçekleşen − beklenen maliyet farkı aynı planın fiyat sapmasıdır; tasarruf değildir.')
        with st.expander('Yöntem ve doğrulama'):solution_note(a)
    elif page==PAGES[4]:
        records,errors=history(root)
        st.write('Önceden oluşturulan planları seçerek açın. Geçmiş kayıt açılması yeni hesaplama başlatmaz.')
        if errors:st.warning(str(len(errors))+' kayıt okunamadı.');st.expander('Okunamayan kayıtlar').write(errors)
        if not records:st.info('Kayıtlı plan yok.');return
        table(formatted(pd.DataFrame([{k:v for k,v in x.items() if k not in ('raw','folder')} for x in records])))
        i=st.selectbox('İncelenecek plan',range(len(records)),format_func=lambda i:str(i+1)+'. '+records[i]['Dönem']+' · '+records[i]['Oluşturulma'])
        if st.button('Seçili Planı Aç',type='primary'):
            st.session_state.run_folder=records[i]['folder'];st.session_state.plan_origin='Geçmiş kayıt';st.success('Geçmiş plan seçildi. Üretim Çizelgesi veya Enerji ve Maliyet sayfasını açabilirsiniz.')
        with st.expander('Kayıt ayrıntıları'):
            d=records[i]['raw']['decision'];st.write('Teknik kayıt kimliği: '+d['run_id']);st.write('Kesin optimum: '+('Tolerans içinde doğrulandı' if d['solver']['tolerans_icinde_optimum'] else 'Kanıtlanmadı'))
