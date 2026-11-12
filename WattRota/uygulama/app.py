from pathlib import Path
import json,sys,subprocess,uuid
from html import escape
import pandas as pd
import streamlit as st
from service import check_connection,available_through,DECISION
from execution import run_worker
from analytics import load_analysis,number,money,time_label,date_label
from charts import style,price_chart,linked_price_gantt,cost_chart,daily_chart,energy_chart

ROOT=Path(__file__).resolve().parent
PAGES=['Üretim Çizelgesi','Analiz ve Bulgular','Üretim Planlama']
st.set_page_config(page_title='WattRota | Elektrik Fiyat Tahminine Dayalı Üretim Çizelgeleme Platformu',layout='wide')
st.markdown('''<style>
.stApp{background:#f3f6f9;color:#17344f}.block-container{max-width:1320px;padding:2rem 2.5rem 3rem}
h1{font-size:1.8rem!important;letter-spacing:-.03em;margin-bottom:.1rem!important}h2{font-size:1.14rem!important;padding-top:.5rem!important}h3{font-size:1rem!important}p{line-height:1.55}
[data-testid="stSidebar"]{background:#17344f}[data-testid="stSidebar"] *{color:#e6eef5!important}
[data-testid="stSidebar"] button,[data-testid="stSidebar"] [data-baseweb="select"] *{color:#17344f!important}
[data-testid="stSidebar"] [data-testid="stExpander"]{border-color:#4b6074}
[data-testid="stMetric"]{background:white;border:1px solid #dde5ec;border-radius:8px;padding:15px 18px;min-height:107px}
[data-testid="stMetricValue"]{font-size:1.45rem!important;color:#17344f;font-variant-numeric:tabular-nums}
[data-testid="stMetricLabel"]{color:#5a6e80}.stButton>button[kind="primary"]{background:#14766f;border-color:#14766f}
[data-testid="stVerticalBlockBorderWrapper"]{background:white;border-radius:8px}[data-testid="stToolbar"]{visibility:hidden}
[data-testid="stCaptionContainer"]{color:#63778b;font-size:.85rem}
.wr-caption{font-size:.84rem!important;color:#526579!important;line-height:1.5;margin:.35rem 0 .65rem}
[data-testid="stCaptionContainer"] *{color:#536a7f!important}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *{color:#b5c6d5!important}
[data-testid="stSidebar"] button *{color:#17344f!important}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"], [data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"] *{color:#17344f!important}
[data-testid="stSidebar"] [data-testid="stExpander"] summary{background:#1e3c57}
</style>''',unsafe_allow_html=True)
@st.cache_data(show_spinner=False)
def analysis(folder):return load_analysis(folder)
def go_plan():st.session_state.nav=PAGES[2]
def metrics(values):
    for col,(name,value) in zip(st.columns(len(values)),values):col.metric(name,value)
def plot(chart):st.altair_chart(chart,width='content' if type(chart).__name__=='VConcatChart' else 'stretch',theme=None)
def caption(text):st.markdown('<p class="wr-caption">'+escape(text)+'</p>',unsafe_allow_html=True)
def table(frame):st.dataframe(frame,hide_index=True,width='stretch')
def no_plan():
    with st.container(border=True):
        st.subheader('Henüz plan seçilmedi')
        st.write('Hazır fabrika için yeni bir üretim planı oluşturun. Önceki hesaplamalar kendiliğinden yeni sonuç olarak gösterilmez.')
        st.button('Üretim Planlamaya Git',on_click=go_plan,type='primary')
def solution_note(a):
    s=a['decision']['solver']
    st.info('Çözücü, tanımlanan tolerans içinde en iyi çözümü doğruladı.' if s['tolerans_icinde_optimum'] else 'Uygulanabilir plan bulundu; kesin optimum kanıtlanmadı. Son ana aramanın optimalite açığı %'+number(s['goreli_acik']*100)+'.')
    with st.expander('Arama süreleri ve doğrulama ayrıntıları'):
        if a['decision'].get('search',{}).get('local_search_enabled'):
            st.write('Mevcut yerel ön iyileştirme kullanıldı. Ön arama bütçesi 4 alt problem × 10 saniye; ana arama sınırı '+number(s['sure_siniri_saniye'],0)+' saniye. Toplam süreç güvenlik sınırı 150 saniye.')
        else:st.write('Bu kayıt önceki, yerel ön iyileştirmesiz hesaplamaya aittir.')
        st.write('Gerçek ön arama: **'+number(s['yerel_arama_saniye'])+' sn** · Ana arama: **'+number(s['sure_saniye'])+' sn** · Toplam solver araması: **'+number(s['toplam_cozum_saniye'])+' sn**')
        if 'total_process_seconds' in a['result']:st.write('Veri okuma, tahmin, model, doğrulama ve gerçekleşen değerlendirme dahil: **'+number(a['result']['total_process_seconds'])+' sn**')
        st.write('Üretim ve yükleme bağımsız kontrolü geçti. Alt sınır '+money(s['alt_sinir_tl'])+'; bu sınır planlama fiyatlarına aittir.')
def equality_note(a):
    c,e=a['comparison'],a['evaluation']
    if c['identical']:
        st.info('Üretim kararları, ürün/iş emri atamaları ve siparişlerin saatlik yükleme miktarları referansla aynı.'+(' İki çizelgenin gerçek maliyetleri de aynı.' if a['use_actual'] else ' Gerçekleşen maliyet henüz değerlendirilemedi.'))
    elif c['production_identical']:st.info('Üretim çizelgesi referansla aynı; siparişlerin yükleme dağılımı farklı. Maliyet eşitliği ayrı değerlendirilir.')
    elif a['use_actual'] and abs(e['actual_advantage_tl'])<.02:st.info('Çizelgeler farklı, ancak gerçek fiyatlarla toplam maliyetleri aynı. Bunun nedeni ayrıca kanıtlanmış değildir.')
    else:st.write('Referansa göre '+number(c['changed_resource_hours'],0)+' üretim kaynak-saati değişti.')


from simple_pages import render
render(ROOT,metrics,plot,caption,table,solution_note)
