import sys,json
from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
before=set((ROOT/'runs').glob('*/result.json'))
app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=180).run()
assert not app.exception
app.sidebar.radio[0].set_value('Hazır Fabrika Planlaması').run()
next(b for b in app.button if b.label=='Bağlantıyı Kontrol Et').click().run()
assert not app.exception and len(app.error)==0
next(b for b in app.button if b.label=='Üretim Planını Oluştur').click().run(timeout=180)
assert not app.exception,[e.message for e in app.exception]
assert len(app.error)==0,[e.value for e in app.error]
after=set((ROOT/'runs').glob('*/result.json'));new=after-before
assert len(new)==1,'Buton yeni bir kayıtlı çözüm üretmeli.'
record=json.loads(next(iter(new)).read_text(encoding='utf-8'))
assert record['success'] and record['decision']['independent_validation']
assert record['decision']['solver']['sure_saniye']>0
assert record['decision']['search']['local_search_enabled']
assert len(record['decision']['solver']['baslangic_iyilestirmeleri'])==4
assert record['decision']['solver']['yerel_arama_saniye']>0
assert record['total_process_seconds']>=record['decision']['solver']['toplam_cozum_saniye']
assert record['evaluation']['actual_advantage_tl']==record['evaluation']['reference_actual_cost_tl']-record['evaluation']['actual_cost_tl']
for page in ['Genel Bakış','Üretim ve Maliyet Analizi','Tahmin ve Gerçekleşen']:
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception,[e.message for e in app.exception]
    assert len(app.error)==0
    assert set((ROOT/'runs').glob('*/result.json'))==after,'Sayfa geçişi yeniden optimizasyon başlatmamalı.'
print(json.dumps({'app_pages_passed':4,'real_button_started_new_solve':True,'run_id':record['run_id'],'solver':record['decision']['solver'],'evaluation':record['evaluation']},ensure_ascii=False))
