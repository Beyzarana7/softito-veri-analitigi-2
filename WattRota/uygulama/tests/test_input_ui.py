import sys,unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from test_user_input import TEMPLATE,altered

class Upload(BytesIO):
    name='kullanici.xlsx'

class InputUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(ROOT/'app.py'));app.session_state['nav']='Üretim Planlama';app.session_state['planning_mode']='Kendi Planını Oluştur';return app
    def test_valid_upload_and_navigation_never_solve(self):
        before=set((ROOT/'runs').glob('*/result.json'))
        with patch('streamlit.file_uploader',return_value=Upload(TEMPLATE.read_bytes())),patch('execution.run_worker',side_effect=AssertionError('Optimizasyon çağrılmamalı')):
            app=self.app().run(timeout=30);self.assertFalse(app.exception)
            next(b for b in app.button if b.label=='Verileri Kontrol Et').click().run(timeout=30)
            self.assertFalse(app.exception);self.assertTrue(any('Veri yapısı' in s.value for s in app.success))
            app.sidebar.radio[0].set_value('Üretim Çizelgesi').run(timeout=30)
            self.assertFalse(app.exception)
            app.sidebar.radio[0].set_value('Üretim Planlama').run(timeout=30)
            self.assertFalse(app.exception);self.assertTrue(any(b.label=='Üretim Planını Oluştur' for b in app.button))
            self.assertTrue(app.session_state['user_validation'].valid)
        self.assertEqual(before,set((ROOT/'runs').glob('*/result.json')))
    def test_invalid_upload_shows_turkish_error(self):
        with patch('streamlit.file_uploader',return_value=Upload(altered('kaynak_urun','C2',-10))),patch('execution.run_worker',side_effect=AssertionError('Optimizasyon çağrılmamalı')):
            app=self.app().run(timeout=30)
            next(b for b in app.button if b.label=='Verileri Kontrol Et').click().run(timeout=30)
            self.assertFalse(app.exception);self.assertTrue(app.error)
            self.assertTrue(any('Pozitif' in e['Düzeltme'] for e in app.session_state['user_validation'].errors))
    def test_template_download_without_upload(self):
        app=self.app().run(timeout=30);self.assertFalse(app.exception)
        self.assertEqual(len(app.get('download_button')),1)

if __name__=='__main__':unittest.main(verbosity=2)
