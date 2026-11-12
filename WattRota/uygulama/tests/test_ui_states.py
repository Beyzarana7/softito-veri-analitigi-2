from pathlib import Path
import sys,copy,unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import streamlit as st
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics import load_analysis
class UIStateTests(unittest.TestCase):
    def test_empty_state_does_not_restore_old_plan(self):
        before=set((ROOT/'runs').glob('*/result.json'))
        app=AppTest.from_file(str(ROOT/'app.py')).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Henüz plan seçilmedi' in x.value for x in app.subheader))
        self.assertEqual(len(app.metric),3)
        self.assertEqual(before,set((ROOT/'runs').glob('*/result.json')))
    def test_unavailable_actuals_have_no_savings(self):
        folder=ROOT/'tests/fixtures/referansla_ayni_plan'
        a=copy.deepcopy(load_analysis(folder));a['use_actual']=False;a['mae']=None
        a['evaluation']={'status':'Henüz değerlendirilemedi'}
        a['prices']=a['prices'].drop(columns=['gercek_fiyat_tl_mwh'])
        st.cache_data.clear()
        with patch('product_pages.load_analysis',return_value=a):
            app=AppTest.from_file(str(ROOT/'app.py'));app.session_state['run_folder']=str(folder)
            app.run(timeout=30);app.sidebar.radio[0].set_value('Enerji ve Maliyet').run(timeout=30)
            self.assertFalse(app.exception,[e.message for e in app.exception])
            metrics={m.label:m.value for m in app.metric}
            self.assertEqual(metrics['Gerçekleşen plan maliyeti'],'Henüz değerlendirilemedi')
            self.assertEqual(metrics['Gerçek − beklenen fark'],'Henüz değerlendirilemedi')
        st.cache_data.clear()
if __name__=='__main__':unittest.main(verbosity=2)
