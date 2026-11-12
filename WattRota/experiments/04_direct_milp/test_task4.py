"""Metrikler, bilgi kesimi ve mevcut MILP ile matris eşdeğerliği."""
import copy
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

import highspy
import numpy as np
import pandas as pd

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT));sys.path.insert(0,str(PROJECT/'src'))
from forecasting import planning_prices
from metrics import decision_metrics,aggregate_capture
import firma_cizelgeleme as original
import solver
from kod.db import create_db_engine,read_firm


class DecisionTests(unittest.TestCase):
    def test_regret_interval(self):
        r=decision_metrics(120,100,90,80)
        self.assertEqual((r['regret_lower_tl'],r['regret_upper_tl']),(10,20))
        self.assertIsNone(r['exact_regret_tl'])
        self.assertAlmostEqual(r['information_capture_vs_incumbent'],2/3)

    def test_better_than_incumbent_and_exact(self):
        r=decision_metrics(120,85,90,80)
        self.assertEqual(r['oracle_incumbent_gap_tl'],-5)
        self.assertEqual((r['regret_lower_tl'],r['regret_upper_tl']),(0,5))
        self.assertTrue(r['beats_oracle_incumbent'])
        self.assertEqual(decision_metrics(120,100,90,90)['exact_regret_tl'],10)

    def test_aggregate_ratio_and_zero(self):
        r=aggregate_capture(30,40,60)
        self.assertEqual((r['capture_vs_incumbent'],r['capture_lower'],r['capture_upper']),(.75,.5,.75))
        self.assertIsNone(aggregate_capture(0,0,0)['capture_vs_incumbent'])
        self.assertEqual(aggregate_capture(-10,20,40)['capture_lower'],-.5)

    def test_unknown_prices_never_enter_objective(self):
        a=pd.Series(np.arange(72,dtype=float),index=pd.date_range('2026-01-05',periods=72,freq='h'))
        for day in (0,1):
            cut=(day+1)*24
            forecast=pd.Series(100.,index=a.index[cut:])
            poisoned=a.copy();poisoned.iloc[cut:]=1e9
            p=planning_prices(a,day,forecast)
            pd.testing.assert_series_equal(p,planning_prices(poisoned,day,forecast))
            pd.testing.assert_series_equal(p.iloc[:cut],a.iloc[:cut])
        pd.testing.assert_series_equal(planning_prices(a,2),a)

    def test_pool_signature_ignores_integer_float_representation(self):
        from run import signature
        plan=pd.DataFrame(dict(kaynak_id=['H01'],tarih_saat=[pd.Timestamp('2026-01-05')],durum=['kapali'],urun_id=[''],is_emri_id=['']))
        loads=pd.DataFrame(dict(siparis_id=['SP01'],kaynak_id=['Y01'],tarih_saat=[pd.Timestamp('2026-01-05')],miktar_ton=[80]))
        floating=loads.copy();floating['miktar_ton']=floating['miktar_ton'].astype(float)
        self.assertEqual(signature(plan,loads,'2026-01-05'),signature(plan,floating,'2026-01-05'))


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine=create_db_engine(PROJECT)
        try:cls.firm=read_firm(engine)
        finally:engine.dispose()

    def capture(self,function,prefix=0):
        captured={};real=highspy.Highs
        class Probe(real):
            def passModel(self,lp):
                captured['lp']=lp
                return super().passModel(lp)
            def run(self):
                self.setOptionValue('mip_max_nodes',0)
                return super().run()
        kwargs=dict(zaman_siniri=3,goreli_acik=.001,yerel_iyilestirme=False)
        if function is solver.solve:kwargs['fixed_prefix_hours']=prefix
        with patch.object(highspy,'Highs',Probe):result=function(self.firm,**kwargs)
        return captured['lp'],result

    def test_original_matrix_preserved(self):
        a,_=self.capture(original.firma_cizelgele)
        b,_=self.capture(solver.solve)
        for attr in ('num_col_','num_row_','offset_'):self.assertEqual(getattr(a,attr),getattr(b,attr))
        for attr in ('col_cost_','col_lower_','col_upper_','row_lower_','row_upper_','integrality_'):
            np.testing.assert_array_equal(getattr(a,attr),getattr(b,attr))
        for attr in ('start_','index_','value_'):
            np.testing.assert_array_equal(getattr(a.a_matrix_,attr),getattr(b.a_matrix_,attr))

    def test_executed_prefix_is_fixed_and_valid(self):
        from run import assert_prefix
        ref_stocks=original.maliyet_ve_ozet(self.firm,self.firm['referans_plan'],self.firm['referans_yuklemeler'])[0]
        previous=(self.firm['referans_plan'],self.firm['referans_yuklemeler'],ref_stocks)
        start=self.firm['tesis_takvimi']['tarih_saat'].min()
        for hours in (24,48):
            lp,result=self.capture(solver.solve,hours)
            names=lp.col_names_
            past=[i for i,name in enumerate(names) if int(re.search(r',([0-9]+)\]$',name).group(1))<hours]
            self.assertEqual(len(past),result[-1]['fixed_columns'])
            self.assertGreater(len(past),0)
            np.testing.assert_array_equal(np.asarray(lp.col_lower_)[past],np.asarray(lp.col_upper_)[past])
            assert_prefix(previous,result,start+pd.Timedelta(hours=hours))
            self.assertTrue(result[-1]['bagimsiz_plan_kontrolu'])


if __name__=='__main__':unittest.main(verbosity=2)
