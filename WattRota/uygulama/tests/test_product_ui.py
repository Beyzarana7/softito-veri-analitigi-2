from pathlib import Path
import sys,unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

class ProductUITests(unittest.TestCase):
    def test_empty_uploader_callback_cannot_erase_saved_data(self):
        from input_page import upload_changed
        data={'widget':None,'user_upload_snapshot':{'content':b'original'},'user_validation':'saved'}
        with patch('input_page.st.session_state',data):upload_changed('widget')
        self.assertEqual(data['user_upload_snapshot']['content'],b'original');self.assertEqual(data['user_validation'],'saved')
    def test_all_pages_from_saved_record_without_solving(self):
        with patch('planning_page.run_worker',side_effect=AssertionError('Yeni optimizasyon yasak')):
            app=AppTest.from_file(str(ROOT/'app.py'));app.session_state['run_folder']=str(ROOT/'runs/20261111_232421_67cf3c75');app.session_state['plan_origin']='Geçmiş kayıt';app.run(timeout=45)
            self.assertFalse(app.exception,[x.message for x in app.exception])
            for name in ['Üretim Planlama','Üretim Çizelgesi','Enerji ve Maliyet','Plan Geçmişi','Kontrol Paneli']:
                app.sidebar.radio[0].set_value(name).run(timeout=45)
                self.assertFalse(app.exception,[x.message for x in app.exception])
    def test_ready_factory_button_preserves_worker_wiring(self):
        import json
        from types import SimpleNamespace
        folder=str(ROOT/'runs/20261111_232421_67cf3c75')
        with patch('planning_page.run_worker',return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'run_folder':folder}))) as worker:
            app=AppTest.from_file(str(ROOT/'app.py'));app.session_state['nav']='Üretim Planlama';app.run(timeout=30)
            next(b for b in app.button if b.label=='Üretim Planını Oluştur').click().run(timeout=45)
            worker.assert_called_once_with(ROOT,timeout=150)
            self.assertEqual(app.session_state['plan_origin'],'Yeni hesaplama')
    def test_empty_state_never_autoloads_history(self):
        app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
        self.assertFalse(app.exception);self.assertTrue(any(s.value=='Henüz plan seçilmedi' for s in app.subheader))

if __name__=='__main__':unittest.main(verbosity=2)
