from pathlib import Path
import sys,unittest,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics import load_analysis
from engineering import engineering

class EngineeringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=load_analysis(ROOT/'runs/20261111_232421_67cf3c75');cls.e=engineering(cls.a)
    def test_daily_cost_reconciliation(self):
        day=self.e['daily'];a=self.a
        for c,target in [('Beklenen maliyet (TL)',a['decision']['expected_cost_tl']),('Gerçekleşen maliyet (TL)',a['evaluation']['actual_cost_tl']),('Referans gerçek maliyeti (TL)',a['evaluation']['reference_actual_cost_tl']),('Avantaj (TL)',a['evaluation']['actual_advantage_tl'])]:self.assertAlmostEqual(day[c].sum(),target,places=6)
        np.testing.assert_allclose(day['Referans gerçek maliyeti (TL)']-day['Gerçekleşen maliyet (TL)'],day['Avantaj (TL)'])
    def test_resource_energy_reconciliation(self):
        energy=self.e['machine_energy']
        self.assertAlmostEqual(energy.loc[energy.Plan=='WattRota','Enerji (kWh)'].sum()+self.e['base_energy'],self.a['energy'].toplam_enerji_kwh_plan.sum())
        self.assertAlmostEqual(energy.loc[energy.Plan=='Referans','Enerji (kWh)'].sum()+self.e['base_energy'],self.a['energy'].toplam_enerji_kwh_ref.sum())
    def test_status_partition_and_utilization(self):
        f=self.e['machines'];np.testing.assert_allclose(f[['Aktif (saat)','Bekleme (saat)','Bakım (saat)','Çalışma dışı (saat)']].sum(axis=1),72)
        np.testing.assert_allclose(f['Aktif (saat)'],f[['Üretim (saat)','Yükleme (saat)','Ürün değişimi (saat)']].sum(axis=1))
        np.testing.assert_allclose(f['Kullanım (%)'],100*f['Aktif (saat)']/f['Uygun (saat)'])
    def test_quantities_not_double_counted(self):
        self.assertEqual(self.e['produced_tonnes'],6720)
        self.assertEqual(self.e['performance']['WattRota üretim (ton)'].sum(),6720)
        self.assertEqual(self.e['performance']['Teslim (ton)'].sum(),6720)
        self.assertEqual(self.e['performance']['Tamamlanan sipariş'].sum(),18)
        for p,g in self.e['distribution'].groupby('Plan'):self.assertEqual(g['Üretim (ton)'].sum(),6720)
    def test_loading_changes_are_visible(self):
        self.assertFalse(self.e['changes'].empty)
        self.assertTrue((self.e['changes']['Referans yükleme (ton)'].fillna(0)!=self.e['changes']['WattRota yükleme (ton)'].fillna(0)).any())
    def test_missing_actuals_are_unavailable(self):
        import copy
        a=copy.deepcopy(self.a);a['use_actual']=False;e=engineering(a)
        self.assertTrue(e['daily']['Gerçekleşen maliyet (TL)'].isna().all())
        self.assertTrue(e['daily']['Avantaj (TL)'].isna().all())

if __name__=='__main__':unittest.main(verbosity=2)
