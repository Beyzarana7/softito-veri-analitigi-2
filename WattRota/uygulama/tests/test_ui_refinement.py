from pathlib import Path
import sys,unittest,csv
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from view_helpers import clean_change_table,change_summary
from product_pages import formatted
from simple_pages import analysis,choose_default

class RefinementTests(unittest.TestCase):
    def test_technical_information_has_one_home(self):
        with patch('planning_page.run_worker',side_effect=AssertionError('Yeni çözüm yasak')):
            app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=40)
            self.assertFalse(app.exception)
            forbidden={'Kavramlar ve yöntem ayrıntıları','Hesaplama ayrıntıları','Planın kapsamı ve uygunluk','Arama süreleri ve doğrulama ayrıntıları','Başlangıç planı ve desteklenen kapsam'}
            for page,count in [('Üretim Çizelgesi',0),('Analiz ve Bulgular',0),('Üretim Planlama',1)]:
                app.sidebar.radio[0].set_value(page).run(timeout=40)
                self.assertFalse(app.exception,[x.message for x in app.exception])
                labels=[e.label for e in app.expander]
                self.assertEqual(labels.count('Teknik Bilgiler'),count);self.assertFalse(set(labels)&forbidden)
    def test_all_machine_mode_and_individual_selection(self):
        app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=40)
        self.assertEqual(app.multiselect[0].value,['Tüm makineler']);self.assertFalse(app.multiselect[0].proto.disabled)
        names=[x for x in app.multiselect[0].options if x!='Tüm makineler']
        app.multiselect[0].set_value(['Tüm makineler',names[0]]).run(timeout=30)
        self.assertEqual(app.multiselect[0].value,[names[0]]);self.assertFalse(app.exception)
        app.multiselect[0].set_value([names[0],'Tüm makineler']).run(timeout=30)
        self.assertEqual(app.multiselect[0].value,['Tüm makineler'])
        app.multiselect[0].set_value(names).run(timeout=30)
        self.assertEqual(app.multiselect[0].value,['Tüm makineler']);self.assertFalse(app.multiselect[0].proto.disabled)
    def test_no_python_missing_labels_in_display(self):
        frame=pd.DataFrame({'Referans iş emri':[None,'None','NaN','<NA>'],'WattRota durumu':['uretim','','nan',None],'Miktar':[1.,float('nan'),2.,3.]})
        shown=formatted(clean_change_table(frame))
        for value in shown.astype(str).to_numpy().flatten():self.assertNotIn(value,{'None','NaN','nan','<NA>'})
        self.assertTrue(pd.isna(clean_change_table(frame).Miktar.iloc[1]))
    def test_change_counts_match_actual_plan_rows(self):
        a=analysis(choose_default(ROOT));summary,changes=change_summary(a)
        self.assertEqual(int(summary['Değişen saat kaydı'].sum()),len(changes))
        self.assertEqual(len(summary),len(a['firm']['kaynaklar']))
        self.assertTrue((summary['Mevcut aktif (saat)']==summary['Önerilen aktif (saat)']).all())
        self.assertGreater(int(summary['Değişen saat kaydı'].sum()),0)
    def test_monthly_view_matches_existing_eda_input(self):
        view=pd.read_csv(ROOT/'analysis_data/aylik_fiyat_profili.csv');self.assertEqual(len(view),20)
        self.assertEqual(set(view.yil),{2024,2025});self.assertEqual(set(view.ay),set(range(1,11)))
        raw=ROOT.parent / 'data/raw/epias'
        for year in (2024,2025):
            values={m:[] for m in range(1,11)}
            with next(raw.glob(f'*0101{year}*.csv')).open(encoding='utf-8-sig') as file:
                for row in csv.DictReader(file,delimiter=';'):
                    month=int(row['Tarih'].split('.')[1])
                    if month in values:values[month].append(float(row['PTF (TL/MWh)'].replace('.','').replace(',','.')))
            for month,prices in values.items():
                record=view[(view.yil==year)&(view.ay==month)].iloc[0]
                self.assertAlmostEqual(record.ortalama_ptf,sum(prices)/len(prices),places=7);self.assertEqual(int(record.saat_sayisi),len(prices))

if __name__=='__main__':unittest.main(verbosity=2)
