"""Yalnız veri yükleme ekranı; hazır fabrika servisinden bağımsızdır."""
from pathlib import Path
import hashlib
import pandas as pd
import streamlit as st
from user_input import SCHEMA, validate_upload

def remember_upload(upload):
    """Widget sayfadan kaldırıldığında silinmeyen, oturuma özel dosya kopyası."""
    if upload is None:return
    content=upload.getvalue()
    snapshot={'name':upload.name,'content':content,'hash':hashlib.sha256(content).hexdigest()}
    old=st.session_state.get('user_upload_snapshot')
    if old is None or (old['name'],old['hash'])!=(snapshot['name'],snapshot['hash']):
        st.session_state.user_upload_snapshot=snapshot
        for key in ('user_validation','user_validation_hash','user_upload_hash'):
            st.session_state.pop(key,None)

def upload_changed(widget_key):
    upload=st.session_state.get(widget_key)
    # Streamlit sayfa dönüşünde widget'ı boş değerle yeniden kurabilir.
    # Kalıcı oturum kopyası yalnız açık sıfırlama isteğiyle silinir.
    if upload is not None:remember_upload(upload)

def clear_data():
    for key in ('user_upload_snapshot','user_validation','user_validation_hash','user_upload_hash'):
        st.session_state.pop(key,None)

def reset_upload():
    clear_data()
    st.session_state.user_uploader_generation=st.session_state.get('user_uploader_generation',0)+1

def render(show_scope=True):
    st.markdown('''<style>
    [data-testid="stFileUploader"] button[kind="secondary"] [data-testid="stMarkdownContainer"] p{font-size:0}
    [data-testid="stFileUploader"] button[kind="secondary"] [data-testid="stMarkdownContainer"] p::after{content:"Dosya seç";font-size:.875rem}
    [data-testid="stFileUploader"] small{display:none}
    </style>''',unsafe_allow_html=True)
    st.write('Üretim verilerinizi Excel şablonuna girin ve veri yapısını kontrol edin.')
    st.info('Bu bölüm veri hazırlama içindir. Optimizasyon çalıştırılmaz. Kontrolü geçen dosya, uygulanabilir bir üretim çizelgesinin varlığını kanıtlamaz.')
    left,right=st.columns(2)
    with left,st.container(border=True):
        st.subheader('1. Şablonu indirin')
        st.write('Örnek çimento fabrikasının kayıtları ve her alanın Türkçe açıklaması şablonda bulunur. Örnekleri kendi verilerinizle değiştirirken sayfa ve sütun adlarını koruyun.')
        template=Path(__file__).resolve().parent/'outputs/veri_girisi/WattRota_Uretim_Verisi_Sablonu.xlsx'
        st.download_button('Excel Şablonunu İndir',template.read_bytes(),file_name=template.name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with right,st.container(border=True):
        st.subheader('2. Doldurduğunuz dosyayı yükleyin')
        st.caption('Yalnız .xlsx; en fazla 5 MB. Formüller, makrolar ve dış bağlantılar kabul edilmez. Veriler oturum belleğinde tutulur; hazır fabrikanın veritabanına yazılmaz.')
        widget_key='user_workbook_'+str(st.session_state.get('user_uploader_generation',0))
        upload=st.file_uploader('Üretim verisi',type=['xlsx'],max_upload_size=5,key=widget_key,on_change=upload_changed,args=(widget_key,))
        remember_upload(upload)
        snapshot=st.session_state.get('user_upload_snapshot')
        if snapshot:
            st.write('Oturumda saklanan dosya: **'+snapshot['name']+'**')
            st.caption('Sayfa değiştirdiğinizde dosya ve kontrol sonucu korunur. Yeni dosya seçerseniz önceki kontrol sonucu temizlenir. Dosyayı oturumdan kaldırmak için aşağıdaki sıfırlama düğmesini kullanın. Tarayıcı oturumu kapanınca kalıcı kayıt tutulmaz.')
            st.button('Yüklenen Verileri Sıfırla',on_click=reset_upload)
    snapshot=st.session_state.get('user_upload_snapshot')
    if snapshot:
        if st.button('Verileri Kontrol Et',type='primary'):
            with st.spinner('Sayfalar, alanlar ve tablo ilişkileri kontrol ediliyor…'):
                st.session_state.user_validation=validate_upload(snapshot['content'],snapshot['name'])
                st.session_state.user_validation_hash=snapshot['hash']
        result=st.session_state.get('user_validation') if st.session_state.get('user_validation_hash')==snapshot['hash'] else None
        if result is None:st.info('Bu dosya henüz kontrol edilmedi. Verileri Kontrol Et düğmesine basın.')
        if result is not None:
            st.subheader('3. Kontrol sonucu')
            if result.valid:
                st.success('Veri yapısı ve tanımlı ilişki kontrolleri geçti. Üretim çizelgesinin uygulanabilirliği henüz doğrulanmadı.')
                st.dataframe(pd.DataFrame([{'Veri grubu':s['sheet'],'Kayıt sayısı':len(result.tables[s['key']])} for s in SCHEMA if s['key'] in result.tables]),hide_index=True,width='stretch')
                if not result.has_reference:st.warning('Başlangıç çizelgesi veya yükleme planı eksik. Motorla planlamadan önce ikisi de hazırlanıp bağımsız olarak doğrulanmalıdır.')
                else:st.caption('Başlangıç çizelgesi ve yükleme kayıtları mevcut. Bunlar yalnız veri yapısı açısından kontrol edildi; stok akışı, minimum çalışma/duruş ve toplam güç gibi fiziksel kısıtların tam doğrulaması sonraki aşamadır.')
            else:
                st.error(f'{len(result.errors)} hata gösteriliyor (en fazla 300). Belirtilen alanları düzeltip dosyayı yeniden yükleyin.')
                st.dataframe(pd.DataFrame(result.errors),hide_index=True,width='stretch')
            if result.tables:
                with st.expander('Yüklenen veriyi incele'):
                    key=st.selectbox('Veri grubu',list(result.tables),format_func=lambda k:next(s['sheet'] for s in SCHEMA if s['key']==k))
                    spec=next(s for s in SCHEMA if s['key']==key)
                    st.dataframe(result.tables[key].rename(columns={f['key']:f['label'] for f in spec['fields']}),hide_index=True,width='stretch')
    if show_scope:
        with st.expander('Başlangıç planı ve desteklenen kapsam'):
            st.write('Motor öğütme, paketleme, dökme ve torbalı yükleme akışını destekler. Başlangıçta üretim kaynakları kapalı, iş emirleri bölünebilir olmalıdır. Genel bir fabrika modelleme aracı değildir.')
            st.write('Başlangıç için her üretim makinesinin 72 saatlik durum/ürün/iş emri çizelgesi ve siparişe bağlı saatlik yüklemeler gerekir. Ayrıca başlangıç ürün ayarı, kapalı kalınan süre, stoklar, hedef stoklar, bakım ve çalışma takvimleri gereklidir.')
            st.write('Sonraki bağlantı aşamasında bu verilerle uyumlu başlangıç planı hazırlanmalı veya kullanıcıdan alınmalı; bağımsız fiziksel doğrulamadan sonra fiyat ve optimizasyon katmanına verilmelidir. Hazır fabrikanın planı değiştirilmiş verilere otomatik olarak atanmaz.')
