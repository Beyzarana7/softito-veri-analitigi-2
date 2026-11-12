from pathlib import Path
import sys,json,unittest
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics import load_analysis,compare_plans
from charts import linked_price_gantt,energy_chart,style,price_chart
class AnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=load_analysis(ROOT/'tests/fixtures/referansla_ayni_plan')
    def test_equal_schedules_include_loading(self):
        a=self.a;self.assertTrue(a['comparison']['identical'])
        changed=a['loads'].copy();changed.loc[0,'miktar_ton']+=1
        c=compare_plans(a['plan'],changed,a['firm']['referans_plan'],a['firm']['referans_yuklemeler'])
        self.assertTrue(c['production_identical']);self.assertFalse(c['loading_identical']);self.assertFalse(c['identical'])
    def test_cost_difference_is_not_savings(self):
        e=self.a['evaluation']
        self.assertAlmostEqual(e['actual_cost_tl'],652799.65895,places=4)
        self.assertAlmostEqual(e['actual_advantage_tl'],0.,places=6)
        self.assertAlmostEqual(e['actual_cost_tl']-e['expected_cost_tl'],45434.51047033,places=4)
    def test_daily_energy_totals_match(self):
        a=self.a;self.assertAlmostEqual(a['daily'].WattRota.sum(),a['evaluation']['actual_cost_tl'],places=5)
        self.assertTrue(np.allclose(a['energy'].fark_kwh,0))
        self.assertAlmostEqual(a['energy'].toplam_enerji_kwh_plan.sum(),a['hourly'].toplam_enerji_kwh.sum())
    def test_maintenance_and_calendar(self):
        a=self.a;g=a['gantt'];self.assertEqual(len(g),5*72)
        self.assertEqual(g.durum.eq('bakim').sum(),6)
        for _,m in a['firm']['bakimlar'].iterrows():
            actual=g[g.kaynak_id.eq(m.kaynak_id)&g.tarih_saat.ge(m.baslangic)&g.tarih_saat.lt(m.bitis)]
            self.assertTrue(actual.Durum.eq('Bakım').all())
    def test_mae_excludes_known_hours(self):
        a=self.a;f=a['prices'][~a['prices'].aciklanmis]
        self.assertEqual(len(f),48)
        self.assertAlmostEqual(a['mae'],(f.planlama_fiyati_tl_mwh-f.gercek_fiyat_tl_mwh).abs().mean())
    def test_localized_chart_specifications(self):
        a=self.a;start=a['decision']['plan_start'];machines=list(a['gantt'].Makine.unique())
        charts=[linked_price_gantt(a['prices'],a['gantt'],start,machines,(0,72),True),energy_chart(a['energy'],start),style(price_chart(a['prices'],start,True))]
        for c in charts:
            s=c.to_json();self.assertIn('Türkiye saati',s);self.assertIn('Ekim',s)
if __name__=='__main__':unittest.main(verbosity=2)
