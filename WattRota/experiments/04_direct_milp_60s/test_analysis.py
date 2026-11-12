"""Maliyet eşitliğiyle çizelge eşitliğini karıştırmayan karşılaştırma testleri."""
import unittest
import pandas as pd
from analyze import compare_schedules


class ComparisonTests(unittest.TestCase):
    def fixtures(self):
        p=pd.DataFrame(dict(kaynak_id=['H01','H01'],tarih_saat=pd.date_range('2026-01-05',periods=2,freq='h'),durum=['uretim','kapali'],urun_id=['UR01',''],is_emri_id=['IE1','']))
        y=pd.DataFrame(dict(siparis_id=['SP1'],kaynak_id=['Y01'],tarih_saat=[pd.Timestamp('2026-01-05')],miktar_ton=[80]))
        return p,y

    def test_row_order_and_numeric_representation(self):
        p,y=self.fixtures();z=y.copy();z['miktar_ton']=z['miktar_ton'].astype(float)
        self.assertTrue(compare_schedules((p,y),(p.iloc[::-1],z))['identical_full_schedule'])

    def test_machine_changes_detected(self):
        p,y=self.fixtures();q=p.copy();q.loc[0,'is_emri_id']='IE2'
        r=compare_schedules((p,y),(q,y))
        self.assertFalse(r['identical_full_schedule']);self.assertEqual(r['changed_machine_resource_hours'],1)
        self.assertTrue(r['identical_loading_schedule'])

    def test_loading_change_detected(self):
        p,y=self.fixtures();z=y.copy();z['tarih_saat']+=pd.Timedelta(hours=1)
        r=compare_schedules((p,y),(p,z))
        self.assertTrue(r['identical_machine_schedule']);self.assertFalse(r['identical_full_schedule'])
        self.assertEqual(r['loading_absolute_difference_ton'],160.)


if __name__=='__main__':unittest.main(verbosity=2)
