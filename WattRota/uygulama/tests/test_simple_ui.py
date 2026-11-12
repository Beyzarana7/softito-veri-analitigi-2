from pathlib import Path
import unittest,sys,json,copy
from unittest.mock import patch
from types import SimpleNamespace
import pandas as pd
import numpy as np
from streamlit.testing.v1 import AppTest
import streamlit as st
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from simple_pages import PAGES,status_by_day,choose_default
from analytics import load_analysis
from service import published_at

class SimpleUITests(unittest.TestCase):
    def test_default_is_verified_and_offline_without_solving(self):
        before=set((ROOT/'runs').glob('*/result.json'))
        with patch('service.create_db_engine',side_effect=AssertionError('Açılışta veritabanı yok')),patch('planning_page.run_worker',side_effect=AssertionError('Açılışta çözüm yok')):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=40)
            self.assertFalse(app.exception,[x.message for x in app.exception])
            self.assertEqual(app.sidebar.radio[0].options,PAGES);self.assertEqual(app.sidebar.radio[0].value,'Üretim Çizelgesi')
            self.assertEqual(app.session_state['plan_origin'],'Doğrulanmış örnek plan')
            folder=Path(app.session_state['run_folder']);r=json.loads((folder/'result.json').read_text(encoding='utf-8'))
            self.assertTrue(r['decision']['independent_validation'])
        self.assertEqual(before,set((ROOT/'runs').glob('*/result.json')))
    def test_all_three_pages_and_filters(self):
        with patch('planning_page.run_worker',side_effect=AssertionError('Çözüm yasak')):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=40)
            app.multiselect[0].set_value(['Öğütme hattı 1']).run(timeout=30)
            next(x for x in app.selectbox if x.label=='Gün').set_value('6 Ekim').run(timeout=30)
            next(x for x in app.radio if x.label=='Gösterilen üretim planı').set_value('Mevcut Üretim Planı').run(timeout=30)
            self.assertFalse(app.exception,[x.message for x in app.exception])
            for name in PAGES:
                app.sidebar.radio[0].set_value(name).run(timeout=40);self.assertFalse(app.exception,[x.message for x in app.exception])
    def test_ready_button_uses_existing_worker(self):
        folder=choose_default(ROOT)
        with patch('planning_page.run_worker',return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'run_folder':folder}))) as worker:
            app=AppTest.from_file(str(ROOT/'app.py'));app.session_state['nav']='Üretim Planlama';app.run(timeout=40)
            next(b for b in app.button if b.label=='Üretim Planını Oluştur').click().run(timeout=40)
            worker.assert_called_once_with(ROOT,timeout=150);self.assertEqual(app.session_state['plan_origin'],'Yeni hesaplama')
    def test_failed_new_plan_is_not_replaced_by_old_demo(self):
        with patch('planning_page.run_worker',return_value=SimpleNamespace(returncode=1,stdout=json.dumps({'error':'Kontrollü test hatası'}))):
            app=AppTest.from_file(str(ROOT/'app.py'));app.session_state['nav']='Üretim Planlama';app.run(timeout=40)
            next(b for b in app.button if b.label=='Üretim Planını Oluştur').click().run(timeout=40)
            app.sidebar.radio[0].set_value('Üretim Çizelgesi').run(timeout=40)
            self.assertNotIn('run_folder',app.session_state)
    def test_known_and_forecast_days_match_decision_time(self):
        a=load_analysis(choose_default(ROOT));p=a['prices'];d=a['decision']
        known=published_at(p.tarih_saat)<=pd.Timestamp(d['historical_decision'])
        np.testing.assert_array_equal(p.aciklanmis.to_numpy(),known)
        byday=status_by_day(p);self.assertEqual(byday.Aciklanmis.tolist(),[24,0,0]);self.assertEqual(byday.Tahmin.tolist(),[0,24,24])
        self.assertEqual(int(byday.Aciklanmis.sum()),d['announced_hours'])
    def test_eda_profile_is_two_full_years(self):
        p=pd.read_csv(ROOT/'analysis_data/saatlik_fiyat_profili.csv')
        self.assertEqual(set(p.yil),{2024,2025});self.assertEqual(len(p),48);self.assertEqual(int(p.saat_sayisi.sum()),17544)
    def test_missing_actuals_are_not_reported_as_savings(self):
        from simple_pages import analysis
        a=copy.deepcopy(load_analysis(choose_default(ROOT)));a['use_actual']=False;a['mae']=None;a['evaluation']={'status':'Henüz değerlendirilemedi'}
        a['prices']=a['prices'].drop(columns='gercek_fiyat_tl_mwh');st.cache_data.clear()
        with patch('simple_pages.load_analysis',return_value=a):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=40)
            self.assertFalse(app.exception,[x.message for x in app.exception])
            self.assertEqual({x.label:x.value for x in app.metric}['Maliyet avantajı'],'Henüz değerlendirilemedi')
            app.sidebar.radio[0].set_value('Analiz ve Bulgular').run(timeout=40)
            self.assertFalse(app.exception,[x.message for x in app.exception])
        st.cache_data.clear()

if __name__=='__main__':unittest.main(verbosity=2)
