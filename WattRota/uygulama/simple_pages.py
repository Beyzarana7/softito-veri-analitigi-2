"""Üç bölümlü sunum. Yeni model veya optimizasyon algoritması içermez."""
from pathlib import Path
import json
import pandas as pd
import streamlit as st
import altair as alt
from analytics import load_analysis,number,money,time_label,date_label,MONTHS
from engineering import engineering
from display_checks import daily_cost_table,schedule_differences,COST_COLUMNS
from charts import axis,with_hour,style,gantt_chart,STATUS
from product_pages import formatted,history
from planning_page import render_ready
from input_page import render as render_input
from view_helpers import clean_change_table,change_summary

PAGES=['Üretim Çizelgesi','Analiz ve Bulgular','Üretim Planlama']
TITLE='Elektrik Fiyat Tahminine Dayalı Üretim Çizelgeleme Platformu'
NAVY='#12324D';TEAL='#00A896';BLUE='#2872DE';CORAL='#E87950';GRAY='#70859A'
STATUS_COLORS=[TEAL,'#F2B64D',BLUE,'#8D8BA5','#DCE6EF','#F2F5F9']
NUM="replace(format(datum.value, ',.0f'), /,/g, '.')"

def choose_default(root):
    candidates=[]
    for file in (root/'runs').glob('*/result.json'):
        try:
            r=json.loads(file.read_text(encoding='utf-8'));d=r['decision']
            if r.get('success') and d.get('independent_validation') and all((file.parent/n).is_file() for n in ('plan.csv','loads.csv','prices.csv')):
                candidates.append((d['created_at'],str(file.parent)))
        except (ValueError,KeyError,TypeError):continue
    return max(candidates)[1] if candidates else None

def initialize_demo(root):
    if not st.session_state.get('demo_initialized'):
        st.session_state.demo_initialized=True
        if not st.session_state.get('run_folder'):
            folder=choose_default(root)
            if folder:st.session_state.run_folder=folder;st.session_state.plan_origin='Doğrulanmış örnek plan'

@st.cache_data(show_spinner=False)
def analysis(folder):
    a=load_analysis(folder);a['engineering']=engineering(a);return a

def status_by_day(prices):
    return prices.assign(Gün=prices.tarih_saat.dt.normalize()).groupby('Gün').agg(
        Aciklanmis=('aciklanmis','sum'),Toplam=('aciklanmis','size')).reset_index().assign(
            Tahmin=lambda f:f.Toplam-f.Aciklanmis)

def price_chart(prices,start,actual):
    f=with_hour(prices,start);f['Saat']=f.tarih_saat.map(time_label)
    parts=[]
    for mask,label in [(f.aciklanmis,'Açıklanmış fiyat'),(~f.aciklanmis,'Tahmin edilen fiyat')]:
        s=f[mask].copy();s['Fiyat türü']=label;s['Fiyat']=s.planlama_fiyati_tl_mwh;parts.append(s)
    if actual:
        s=f[~f.aciklanmis].copy();s['Fiyat türü']='Sonradan açıklanan fiyat';s['Fiyat']=s.gercek_fiyat_tl_mwh;parts.append(s)
    data=pd.concat(parts);data['Tutar']=data.Fiyat.map(lambda x:number(x)+' TL/MWh')
    chart=alt.Chart(data).mark_line(strokeWidth=2.4).encode(x=axis(start),y=alt.Y('Fiyat:Q',title='Elektrik fiyatı (TL/MWh)',axis=alt.Axis(labelExpr=NUM)),
        color=alt.Color('Fiyat türü:N',scale=alt.Scale(domain=['Açıklanmış fiyat','Tahmin edilen fiyat','Sonradan açıklanan fiyat'],range=[TEAL,CORAL,BLUE])),
        strokeDash=alt.condition(alt.datum['Fiyat türü']=='Tahmin edilen fiyat',alt.value([6,3]),alt.value([1,0])),
        tooltip=['Saat:N','Fiyat türü:N','Tutar:N'])
    unknown=f[~f.aciklanmis]
    if len(unknown):chart+=alt.Chart(pd.DataFrame({'saat_no':[unknown.saat_no.min()]})).mark_rule(color=GRAY,strokeDash=[3,3]).encode(x=axis(start))
    return style(chart.properties(height=230))

def question(title):st.subheader(title)

def sync_machine_selection(names):
    selected=list(st.session_state.get('machine_selection',[]))
    previous=st.session_state.get('_previous_machine_selection',['Tüm makineler'])
    if 'Tüm makineler' in selected:
        selected=[x for x in selected if x!='Tüm makineler'] if 'Tüm makineler' in previous and len(selected)>1 else ['Tüm makineler']
    if set(selected)==set(names):selected=['Tüm makineler']
    st.session_state.machine_selection=selected
    st.session_state._previous_machine_selection=selected.copy()

def technical_information(a,table):
    with st.expander('Teknik Bilgiler'):
        st.write('Mevcut üretim planı başlangıç çizelgesidir. Önerilen çizelge mevcut fiyat tahmini ve MILP modeliyle hazırlanır. Teknik sonuç dosyaları ve bağımsız doğrulama kayıtları korunur.')
        st.write('Geçmiş yayın bilgisi önceki gün 14.00 açıklama varsayımına dayanır; yayın gecikmesi ve sonradan veri revizyon arşivi yoktur. Sonradan açıklanan fiyatlar karar girdisine eklenmez.')
        st.write('Üretim, hazırlık, bakım, stok, teslim ve ortak güç koşulları denetlenir. İşler bölünebilir, üretim başlangıcı kapalıdır; bu model her fabrikayı otomatik temsil etmez. Kullanıcı dosyalarının yapısal doğrulaması, fiziksel uygulanabilirlik kanıtı değildir.')
        if a:
            s=a['decision']['solver']
            status='Tolerans içinde doğrulandı' if s.get('tolerans_icinde_optimum') else 'Uygun çözüm; kesin optimum kanıtlanmadı'
            values=[('Çözüm durumu',status)]
            for label,key,unit in [('Ön iyileştirme süresi','yerel_arama_saniye',' sn'),('Ana arama süresi','sure_saniye',' sn'),('Toplam çözüm süresi','toplam_cozum_saniye',' sn'),('Alt sınır — planlama fiyatlarıyla','alt_sinir_tl',' TL')]:
                if s.get(key) is not None:values.append((label,number(s[key])+unit))
            if s.get('goreli_acik') is not None:values.append(('Ana aramanın optimalite açığı','%'+number(100*s['goreli_acik'])))
            values.append(('Bağımsız üretim ve yükleme kontrolü','Geçti' if a['decision'].get('independent_validation') else 'Doğrulanmadı'))
            table(pd.DataFrame(values,columns=['Bilgi','Değer']))
        st.caption('Aylık grafik Notebook 01 §4.4 ile aynı ocak–ekim kapsamını kullanır; saat profili 2024–2025 tam yıllarıdır. Fiyatlar nominal TL cinsindedir. Diğer Notebook’lardaki pilotlar, 19 planlık karşılaştırma ve tam bilgi senaryoları bu seçili planın sonucu olarak sunulmaz.')

def render(root,metrics,plot,caption,table,solution_note):
    st.markdown('''<style>
    .stApp{background:#F4F7FB}.block-container{max-width:1450px;padding:1.5rem 2rem 3rem}
    [data-testid="stSidebar"]{background:#12324D;min-width:230px;max-width:250px}
    .wr-brand{font-size:2.6rem;font-weight:800;letter-spacing:-.075em;color:#FFFFFF!important;margin-bottom:8px;line-height:1.15}.wr-brand span{color:#11D3BC!important}
    .wr-brand::after{content:"";display:block;width:42px;height:3px;background:#11D3BC;margin-top:13px}.wr-tag{color:#BCD9E7;font-size:.76rem;line-height:1.5;margin:13px 0 25px}
    .wr-factory{border:1px solid #31526B;border-left:3px solid #11D3BC;border-radius:6px;padding:12px;margin-top:25px;font-size:.82rem;line-height:1.7;color:#D6E8F1}
    h1{font-size:2.1rem!important;color:#12324D}h2{font-size:1.18rem!important;color:#12324D}
    [data-testid="stMetric"]{background:white;border:1px solid #DCE6EF;border-top:3px solid #00A896;border-radius:8px;padding:12px 14px;min-height:90px}
    [data-testid="stMetricValue"]{font-size:1.35rem!important}.stButton>button[kind="primary"]{background:#008D82;border-color:#008D82}
    </style>''',unsafe_allow_html=True)
    st.sidebar.markdown('<div class="wr-brand">Watt<span>Rota</span></div><div class="wr-tag">'+TITLE+'</div>',unsafe_allow_html=True)
    if st.session_state.get('nav') not in PAGES:st.session_state.nav=PAGES[0]
    page=st.sidebar.radio('Bölümler',PAGES,key='nav',label_visibility='collapsed')
    initialize_demo(root)
    st.title('WattRota');st.caption(TITLE)
    a=None;folder=st.session_state.get('run_folder')
    if folder:
        try:a=analysis(folder)
        except Exception as exc:st.error('Örnek plan okunamadı: '+str(exc))
    st.header(page)
    if a:
        d,e=a['decision'],a['evaluation'];eng=a['engineering'];start=pd.Timestamp(d['plan_start'])
        st.write('**Fabrika:** Sentetik çimento fabrikası · **Dönem:** '+date_label(start,True)+' – '+date_label(start+pd.Timedelta(days=2),True)+' · **Durum:** '+('Üretim koşullarına uygun' if d['independent_validation'] else 'Uygunluk doğrulanmadı'))
        origin=st.session_state.get('plan_origin','Geçmiş plan')
        st.caption('Yeni oluşturulan plan.' if origin=='Yeni hesaplama' else 'Daha önce hesaplanmış ve doğrulanmış örnek plan gösteriliyor. Bu ekranı açmak yeni hesaplama başlatmaz.')
        st.sidebar.markdown('<div class="wr-factory"><strong>Örnek çimento fabrikası</strong><br>'+str(len(a['firm']['urunler']))+' ürün · '+str(len(a['orders']))+' sipariş<br>'+number(a['orders'].miktar_ton.sum(),0)+' ton üretim talebi</div>',unsafe_allow_html=True)
    if page==PAGES[0]:
        if not a:st.info('Seçili plan yok. Üretim Planlama bölümünden bir örnek kayıt seçebilir veya yeni plan oluşturabilirsiniz.');return
        names=a['firm']['kaynaklar'].kaynak_adi.tolist();c1,c2=st.columns([3,1])
        if 'machine_selection' not in st.session_state:
            st.session_state.machine_selection=['Tüm makineler'];st.session_state._previous_machine_selection=['Tüm makineler']
        selection=c1.multiselect('Makineler',['Tüm makineler']+names,key='machine_selection',filter_mode=None,select_all=False,placeholder='Makine seçin',on_change=sync_machine_selection,args=(names,))
        selected=names if 'Tüm makineler' in selection else selection
        days=[date_label(start+pd.Timedelta(days=i)) for i in range(3)]
        day=c2.selectbox('Gün',['Üç gün']+days)
        plan=st.radio('Gösterilen üretim planı',['Mevcut Üretim Planı',"WattRota'nın Önerdiği Plan"],index=1,horizontal=True)
        domain=(0,72) if day=='Üç gün' else (24*days.index(day),24*(days.index(day)+1))
        if not selected:st.info('Çizelge için en az bir makine seçin.');return
        grid=a['gantt'] if plan=="WattRota'nın Önerdiği Plan" else a['reference_gantt']
        chart=gantt_chart(grid,start,selected,domain,height=max(280,35*len(selected)+110)).encode(
            y=alt.Y('Makine:N',title=None,sort=selected,axis=alt.Axis(labelLimit=230,labelFontSize=12,labelPadding=8)),
            color=alt.Color('Durum:N',scale=alt.Scale(domain=STATUS,range=STATUS_COLORS),legend=alt.Legend(columns=3,labelLimit=170)))
        plot(style(chart));caption('Her blok bir saattir. Bakım, çalışma takvimi ve üretim durumları kayıtlı fabrika verilerinden alınır. Ayrıntıları görmek için blokların üzerine gelin.')
        metrics([('Karşılanan sipariş',str(int((a['orders']['karşılama_pct']>=99.999).sum()))+' / '+str(len(a['orders']))),('Üretim koşulları','Uygun' if d['independent_validation'] else 'Doğrulanmadı'),('Maliyet avantajı',money(e['actual_advantage_tl']) if a['use_actual'] else 'Henüz değerlendirilemedi')])
        changes,_=schedule_differences(a,selected,start+pd.Timedelta(hours=domain[0]),start+pd.Timedelta(hours=domain[1]))
        st.subheader('Hangi faaliyetler değişti?')
        if a['comparison']['identical']:st.info('İki üretim planının üretim, ürün, iş emri ve saatlik yükleme kararları aynı.')
        elif changes.empty:st.info('Seçtiğiniz makine ve günlerde değişiklik yok. Diğer saatlerde fark bulunabilir.')
        else:
            if a['comparison']['production_identical']:st.write('Öğütme ve paketleme çizelgesi aynı; siparişlerin yükleme dağılımı değişti.')
            st.write(str(changes.Makine.nunique())+' çalışma noktasında '+str(len(changes))+' saat kaydı farklı.')
            with st.expander('Değişiklik ayrıntıları'):
                table(formatted(clean_change_table(changes)))
                caption('Aynı toplam aktif süre, aynı saatlerde çalışma anlamına gelmez. Yalnız farklı durum, ürün, iş emri veya yükleme miktarı içeren saatler gösterilir.')
    elif page==PAGES[1]:
        if not a:st.info('Analiz için Üretim Planlama bölümünden bir plan seçin.');return
        q1,q2,q3,q4=st.tabs(['Elektrik fiyatları','Tahmin doğruluğu','Maliyet avantajı','Üretim koşulları'])
        with q1:
            question('Elektrik fiyatları zaman içinde nasıl değişiyor?')
            profile=pd.read_csv(root/'analysis_data/saatlik_fiyat_profili.csv');profile['Yıl']=profile.yil.astype(str);profile['Ortalama']=profile.ortalama_ptf.map(lambda x:number(x)+' TL/MWh')
            plot(style(alt.Chart(profile).mark_line(point=True,strokeWidth=2.3).encode(x=alt.X('saat:O',title='Günün saati',sort=list(range(24)),axis=alt.Axis(labelAngle=0)),y=alt.Y('ortalama_ptf:Q',title='Ortalama PTF (TL/MWh)',axis=alt.Axis(labelExpr=NUM)),color=alt.Color('Yıl:N',scale=alt.Scale(domain=['2024','2025'],range=[TEAL,BLUE])),tooltip=['Yıl:N',alt.Tooltip('saat:O',title='Saat'),'Ortalama:N']).properties(height=235)))
            findings=[]
            for year,g in profile.groupby('yil'):
                low=g.loc[g.ortalama_ptf.idxmin()];high=g.loc[g.ortalama_ptf.idxmax()]
                findings.append(str(year)+': en düşük ortalama '+str(int(low.saat)).zfill(2)+'.00, en yüksek ortalama '+str(int(high.saat)).zfill(2)+'.00.')
            st.write('**Bulgu:** '+' '.join(findings))
            caption('Yorum: 2024–2025 tam yıl ortalamaları, planlamada saat seçiminin önemini gösterir; her gün aynı saatlerin ucuz olacağını garanti etmez.')
            monthly=pd.read_csv(root/'analysis_data/aylik_fiyat_profili.csv');monthly['Yıl']=monthly.yil.astype(str);monthly['Ay']=monthly.ay.map(lambda m:MONTHS[int(m)-1]);monthly['Ortalama']=monthly.ortalama_ptf.map(lambda x:number(x)+' TL/MWh')
            st.write('**Aylık değişim · Ocak–Ekim**')
            plot(style(alt.Chart(monthly).mark_line(point=True,strokeWidth=2.3).encode(x=alt.X('Ay:N',title=None,sort=MONTHS[:10],axis=alt.Axis(labelAngle=0)),y=alt.Y('ortalama_ptf:Q',title='Ortalama PTF (TL/MWh)',axis=alt.Axis(labelExpr=NUM)),color=alt.Color('Yıl:N',scale=alt.Scale(domain=['2024','2025'],range=[TEAL,BLUE])),tooltip=['Yıl:N','Ay:N','Ortalama:N']).properties(height=200)))
            result=[]
            for year,g in monthly.groupby('yil'):
                low=g.loc[g.ortalama_ptf.idxmin()];high=g.loc[g.ortalama_ptf.idxmax()]
                result.append(str(year)+': en düşük aylık ortalama '+MONTHS[int(low.ay)-1]+', en yüksek '+MONTHS[int(high.ay)-1]+'.')
            st.write('**Bulgu:** '+' '.join(result));caption('Yorum: Fiyat seviyesi aylara göre de değişir. Mevcut Notebook’taki ocak–ekim karşılaştırması gösterilir; nominal TL farkları tek başına gerçek fiyat artışı olarak yorumlanmaz.')
        with q2:
            question('Elektrik fiyat tahminleri ne kadar doğru?')
            plot(price_chart(a['prices'],start,a['use_actual']))
            status=status_by_day(a['prices']);status['Gün']=status.Gün.map(date_label)
            status['Planlamada kullanılan fiyat']=status.apply(lambda x:'Açıklanmış fiyatlar' if x.Aciklanmis==x.Toplam else 'Fiyat tahmini' if x.Tahmin==x.Toplam else 'Açıklanmış fiyatlar ve tahmin',axis=1)
            table(status[['Gün','Planlamada kullanılan fiyat','Aciklanmis','Tahmin']].rename(columns={'Aciklanmis':'Bilinen saat','Tahmin':'Tahmin edilen saat'}))
            st.write('**Bulgu:** '+('Yalnız tahmin edilen '+str(int(status.Tahmin.sum()))+' saatte ortalama mutlak hata '+number(a['mae'])+' TL/MWh.' if a['mae'] is not None else 'Gerçek fiyatlar tamamlanmadığı için tahmin doğruluğu henüz değerlendirilemedi.'))
            caption('Yorum: Tahminin sapması ile maliyet avantajı farklı sonuçlardır. Sonradan açıklanan fiyatlar burada karşılaştırma içindir; karar girdisi değildir.')
        with q3:
            question('Tahminlere dayalı üretim çizelgeleme maliyet avantajı sağlıyor mu?')
            daily=eng['daily'];chartdata=daily.melt(id_vars=['Tarih'],value_vars=['Gerçekleşen maliyet (TL)','Referans gerçek maliyeti (TL)'],var_name='Üretim planı',value_name='Maliyet')
            chartdata['Üretim planı']=chartdata['Üretim planı'].map({'Gerçekleşen maliyet (TL)':"WattRota'nın Önerdiği Plan",'Referans gerçek maliyeti (TL)':'Mevcut Üretim Planı'})
            chartdata['Tutar']=chartdata.Maliyet.map(lambda x:money(x) if pd.notna(x) else 'Henüz değerlendirilemedi')
            if a['use_actual']:
                plot(style(alt.Chart(chartdata).mark_bar(cornerRadiusEnd=3).encode(x=alt.X('Tarih:N',title=None,sort=daily.Tarih.tolist(),axis=alt.Axis(labelAngle=0)),xOffset='Üretim planı:N',y=alt.Y('Maliyet:Q',title='Maliyet (TL)',axis=alt.Axis(labelExpr=NUM)),color=alt.Color('Üretim planı:N',scale=alt.Scale(domain=['Mevcut Üretim Planı',"WattRota'nın Önerdiği Plan"],range=[GRAY,TEAL])),tooltip=['Tarih:N','Üretim planı:N','Tutar:N']).properties(height=220)))
            view=daily_cost_table(daily).rename(columns={'Tarih':'Gün','Beklenen maliyet (TL)':'Beklenen (TL)','Gerçekleşen maliyet (TL)':'Önerilen · gerçek fiyat (TL)','Referans gerçek maliyeti (TL)':'Mevcut · gerçek fiyat (TL)'})
            table(formatted(view))
            if a['use_actual']:
                advantage=e['actual_advantage_tl'];st.write('**Bulgu:** Seçili üç günlük planda maliyet avantajı '+money(advantage)+'. '+('Önerilen plan daha düşük maliyetli.' if advantage>.01 else 'Önerilen plan daha pahalı.' if advantage<-.01 else 'İki planın maliyeti aynı.'))
                if a['comparison']['production_identical'] and not a['comparison']['loading_identical']:st.write('Bu örnekte öğütme ve paketleme zamanları aynı; değişiklik yükleme dağılımındadır.')
            else:st.info('Gerçek fiyatlar tamamlanmadan gerçek fiyatlı maliyet ve maliyet avantajı gösterilmez.')
            caption('Yorum: Avantaj iki planın aynı gerçek fiyatlarla karşılaştırılmasıdır. Beklenen–gerçek fiyatlı maliyet farkı tasarruf değildir. Bu sonuç seçili örneğe aittir ve fabrikanın fiilen ödediği faturayı göstermez.')
        with q4:
            question('Önerilen çizelgede hangi üretim kararları değişiyor?')
            summary,all_changes=change_summary(a)
            plot(style(alt.Chart(summary).mark_bar(color=TEAL,cornerRadiusEnd=3).encode(y=alt.Y('Makine:N',title=None,axis=alt.Axis(labelLimit=210)),x=alt.X('Değişen saat kaydı:Q',title='Değişen saat kaydı',axis=alt.Axis(tickMinStep=1)),tooltip=['Makine:N','Değişen saat kaydı:Q','Mevcut aktif (saat):Q','Önerilen aktif (saat):Q']).properties(height=230)))
            st.write('**Bulgu:** '+str(int((summary['Değişen saat kaydı']>0).sum()))+' çalışma noktasında toplam '+str(len(all_changes))+' saat kaydı farklı.')
            caption('Yorum: Toplam aktif süre aynı kalsa bile çalışma zamanı veya saatlik yükleme miktarı değişebilir. Sıfır sütun, ilgili makinede bu iki plan arasında karar farkı olmadığını gösterir.')
            with st.expander('Makine bazında kısa karşılaştırma'):table(formatted(summary))
    else:
        st.write('Hazır sentetik çimento fabrikasıyla çalışın. Yeni hesaplama yalnız aşağıdaki düğmeyle başlar.')
        render_ready(root,a,metrics,caption,plot,lambda _:None)
        if a:
            with st.expander('Hazır fabrikanın üretim verileri'):
                tabs=st.tabs(['Ürünler','Makineler','Kapasiteler','Siparişler'])
                with tabs[0]:table(a['firm']['urunler'].rename(columns={'urun_id':'Ürün kodu','urun_adi':'Ürün adı'}))
                with tabs[1]:table(a['firm']['kaynaklar'].rename(columns={'kaynak_id':'Makine kodu','kaynak_adi':'Makine adı','kaynak_turu':'İşlem türü'}).replace({'ogutme':'Öğütme','paketleme':'Paketleme','dokme_yukleme':'Dökme yükleme','torbali_yukleme':'Torbalı yükleme'}))
                with tabs[2]:table(a['firm']['kaynak_urun'].rename(columns={'kaynak_id':'Makine kodu','urun_id':'Ürün kodu','kapasite_ton_saat':'Kapasite (ton/saat)','calisma_gucu_kw':'Elektrik gücü (kW)'}))
                with tabs[3]:table(a['orders'][['Ürün','miktar_ton','teslim_zamani']].assign(teslim_zamani=lambda f:f.teslim_zamani.map(time_label)).rename(columns={'miktar_ton':'Miktar (ton)','teslim_zamani':'Teslim zamanı'}))
        with st.expander('Önceki örnek planlardan birini aç'):
            records,errors=history(root)
            if records:
                selected=st.selectbox('Örnek plan',range(len(records)),format_func=lambda i:records[i]['Dönem']+' · '+records[i]['Oluşturulma'])
                if st.button('Örnek Planı Aç'):
                    st.session_state.run_folder=records[selected]['folder'];st.session_state.plan_origin='Geçmiş örnek plan';st.rerun()
            if errors:st.warning(str(len(errors))+' örnek kaydı okunamadı.')
        with st.expander('İsteğe bağlı Excel veri kontrolü'):
            st.caption('Yalnız dosya yapısı kontrol edilir. Bu veriler hazır fabrikayı değiştirmez ve kullanıcı verileriyle planlama başlatmaz.')
            render_input(show_scope=False)
        technical_information(a,table)
