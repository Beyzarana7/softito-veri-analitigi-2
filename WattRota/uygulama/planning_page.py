from pathlib import Path
import json,subprocess,uuid
import pandas as pd
import streamlit as st
from service import check_connection,available_through,DECISION
from execution import run_worker
from analytics import time_label,number
from charts import price_chart,style

def render_ready(ROOT,a,metrics,caption,plot,solution_note):
    start=pd.Timestamp(a['decision']['plan_start']) if a else None
    with st.container(border=True):
        st.subheader('Örnek çimento fabrikası')
        st.write('İki öğütme hattı, ortak paketleme ve iki yükleme noktası. Üç ürünün dökme ve torbalı teslimatları birlikte planlanır.')
        metrics([('Planlama dönemi','6–8 Ekim 2025'),('Üretim ortamı','Hazır çimento fabrikası'),('Sipariş miktarı','6.720 ton')])
        cutoff=available_through(DECISION);known=int(sum(t<cutoff for t in pd.date_range('2025-10-06',periods=72,freq='h')))
        caption('Planlama anı: '+time_label(DECISION)+' · '+str(known)+' saat açıklanmış, '+str(72-known)+' saat tahmin. Yayın varsayımı Teknik Bilgiler bölümünde açıklanır.')
        c1,c2=st.columns([1,2])
        with c1:
            if st.button('Veri Bağlantısını Kontrol Et'):
                try:st.session_state.connection=check_connection();st.success('Veri bağlantısı doğrulandı.')
                except Exception as exc:st.error('Veri bağlantısı kurulamadı ('+type(exc).__name__+'). Hizmeti ve yerel bağlantı ayarlarını kontrol edin. Başka bir kaynağa geçilmedi.')
        with c2:caption('Yeni plan için fabrika verileri veritabanından yeniden okunur. Örnek plan, yeni hesaplama yerine gösterilmez.')
        if st.button('Üretim Planını Oluştur',type='primary'):
            st.session_state.pop('run_folder',None)
            a=None;folder=None
            with st.status('Üretim planı hesaplanıyor',expanded=True) as status:
                st.write('Fabrika verileri ve fiyatlar hazırlanıyor. Başlangıç planı kontrol edildikten sonra yeni çizelge hesaplanacak ve üretim koşullarına uygunluğu denetlenecek.')
                try:
                    completed=run_worker(ROOT,timeout=150)
                    response=json.loads(completed.stdout.strip().splitlines()[-1])
                    if completed.returncode!=0:raise RuntimeError(response.get('error','Plan oluşturulamadı.'))
                    st.session_state.run_folder=response['run_folder'];st.session_state.plan_origin='Yeni hesaplama';st.session_state.connection={'connected':True}
                    status.update(label='Plan hesaplandı ve doğrulandı',state='complete',expanded=False);st.rerun()
                except subprocess.TimeoutExpired:
                    (ROOT/'runs').mkdir(exist_ok=True)
                    with (ROOT/'runs'/('timeout_'+uuid.uuid4().hex+'.json')).open('x',encoding='utf-8') as f:json.dump({'status':'Uygulama süre sınırı','seconds':150},f)
                    status.update(label='Hesaplama süre sınırında durduruldu',state='error');st.error('150 saniyelik uygulama sınırına ulaşıldı. Eski plan yeni çıktı olarak gösterilmedi.')
                except Exception as exc:status.update(label='Hesaplama tamamlanamadı',state='error');st.error(str(exc))
        caption('Her düğmeye basış yeni bir hesaplamadır. İşlem tamamlandığında yeni plan otomatik olarak açılır.')
    if a:
        st.success('Seçili plan üretim koşullarına uygun. Üretim Çizelgesi bölümünde inceleyebilirsiniz.')
        solution_note(a)
