import sys,unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_user_input import TEMPLATE,altered

class Upload(BytesIO):
    def __init__(self,data,name):super().__init__(data);self.name=name

class SessionTests(unittest.TestCase):
    def test_file_result_errors_replacement_reset(self):
        selected=[Upload(TEMPLATE.read_bytes(),'gecerli.xlsx')]
        with patch('streamlit.file_uploader',side_effect=lambda *a,**k:selected[0]),patch('execution.run_worker',side_effect=AssertionError('Optimizasyon yasak')):
            app=AppTest.from_file(str(ROOT/'app.py'));app.session_state['nav']='Üretim Planlama';app.session_state['planning_mode']='Kendi Planını Oluştur';app.run(timeout=30)
            next(b for b in app.button if b.label=='Verileri Kontrol Et').click().run(timeout=30)
            first=app.session_state['user_validation'];self.assertTrue(first.valid)
            saved=app.session_state['user_upload_snapshot']['content']
            app.sidebar.radio[0].set_value('Üretim Çizelgesi').run(timeout=30)
            selected[0]=None
            app.sidebar.radio[0].set_value('Üretim Planlama').run(timeout=30)
            self.assertFalse(app.exception);self.assertTrue(app.success)
            self.assertEqual(saved,app.session_state['user_upload_snapshot']['content'])
            self.assertIs(first,app.session_state['user_validation'])
            self.assertTrue(app.session_state['user_validation'].tables)
            selected[0]=Upload(altered('kaynak_urun','C2',-1),'hatali.xlsx');app.run(timeout=30)
            self.assertFalse(any('Veri yapısı' in item.value for item in app.success));self.assertNotIn('user_validation',app.session_state)
            next(b for b in app.button if b.label=='Verileri Kontrol Et').click().run(timeout=30)
            errors=app.session_state['user_validation'].errors.copy();self.assertTrue(errors)
            selected[0]=None
            app.sidebar.radio[0].set_value('Üretim Çizelgesi').run(timeout=30)
            app.sidebar.radio[0].set_value('Üretim Planlama').run(timeout=30)
            self.assertEqual(app.session_state['user_validation'].errors,errors);self.assertTrue(app.error)
            next(b for b in app.button if b.label=='Yüklenen Verileri Sıfırla').click().run(timeout=30)
            self.assertFalse(app.exception);self.assertFalse(app.error)
            self.assertNotIn('user_upload_snapshot',app.session_state);self.assertNotIn('user_validation',app.session_state)

if __name__=='__main__':unittest.main(verbosity=2)

