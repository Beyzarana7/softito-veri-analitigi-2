from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
import sys,unittest,copy
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics import load_analysis
from engineering import engineering
from display_checks import daily_cost_table,schedule_differences,COST_COLUMNS

def cents(value):return Decimal(str(value)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)

class FinalFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=load_analysis(ROOT/'runs/20261111_232421_67cf3c75');cls.daily=engineering(cls.a)['daily']
    def test_totals_match_saved_record_to_penny(self):
        table=daily_cost_table(self.daily);row=table.iloc[-1];a=self.a
        targets=[a['decision']['expected_cost_tl'],a['evaluation']['actual_cost_tl'],a['evaluation']['reference_actual_cost_tl'],a['evaluation']['actual_advantage_tl']]
        for c,target in zip(COST_COLUMNS,targets):
            self.assertEqual(cents(row[c]),cents(target))
            self.assertEqual(sum(cents(v) for v in table[c].iloc[:-1]),cents(row[c]))
        self.assertEqual(row.Tarih,'72 Saatlik Toplam');self.assertEqual(len(table),4)
        self.assertEqual(table.columns.tolist(),['Tarih']+COST_COLUMNS)
    def test_date_is_not_summed_even_after_column_reorder(self):
        table=daily_cost_table(self.daily[list(reversed(self.daily.columns))])
        self.assertEqual(table.Tarih.tolist(),['6 Ekim','7 Ekim','8 Ekim','72 Saatlik Toplam'])
        self.assertTrue(all(pd.api.types.is_numeric_dtype(table[c]) for c in COST_COLUMNS))
    def test_unavailable_actuals_never_become_zero(self):
        day=self.daily.copy();day[COST_COLUMNS[1:]]=np.nan;row=daily_cost_table(day).iloc[-1]
        self.assertTrue(pd.notna(row[COST_COLUMNS[0]]));self.assertTrue(row[COST_COLUMNS[1:]].isna().all())
    def test_partial_actuals_do_not_make_complete_total(self):
        day=self.daily.copy();day.loc[0,COST_COLUMNS[1:]]=np.nan
        self.assertTrue(daily_cost_table(day).iloc[-1][COST_COLUMNS[1:]].isna().all())
    def diff(self,a=None,machines=None,start=None,end=None):
        a=a or self.a;t=a['gantt'].tarih_saat
        return schedule_differences(a,machines or a['firm']['kaynaklar'].kaynak_adi.tolist(),start or t.min(),end or t.max()+pd.Timedelta(hours=1))
    def test_real_loading_differences_are_visible(self):
        table,grid=self.diff();self.assertFalse(table.empty);self.assertEqual(len(grid),2*len(table))
        self.assertTrue((table['Referans yükleme (ton)']!=table['WattRota yükleme (ton)']).any())
        self.assertEqual(set(grid.Plan),{'Referans Plan','WattRota Planı'})
    def test_identical_plan_has_no_changes(self):
        a=copy.deepcopy(self.a);a['gantt']=a['reference_gantt'].copy(deep=True)
        table,grid=self.diff(a);self.assertTrue(table.empty);self.assertTrue(grid.empty)
    def test_machine_and_day_filters_apply_to_actual_timestamps(self):
        table,grid=self.diff();name=grid.Makine.iloc[0];start=grid.tarih_saat.iloc[0].normalize();end=start+pd.Timedelta(days=1)
        table,grid=self.diff(machines=[name],start=start,end=end)
        self.assertEqual(set(table.Makine),{name});self.assertTrue(grid.tarih_saat.ge(start).all() and grid.tarih_saat.lt(end).all())
    def test_equal_active_hours_do_not_hide_time_changes(self):
        a=copy.deepcopy(self.a);g=a['reference_gantt'].copy(deep=True);a['gantt']=g
        name=g.loc[g.durum.eq('uretim'),'Makine'].iloc[0]
        active=g.index[g.Makine.eq(name)&g.durum.eq('uretim')][0];idle=g.index[g.Makine.eq(name)&g.durum.eq('kapali')][0]
        fields=['Durum','Ürün','is_emri_id']
        g.loc[[active,idle],fields]=g.loc[[idle,active],fields].to_numpy()
        table,_=self.diff(a,machines=[name]);self.assertEqual(len(table),2)

if __name__=='__main__':unittest.main(verbosity=2)
