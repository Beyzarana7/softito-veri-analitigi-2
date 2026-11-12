"""Takvim, sızıntı, profil dönüşümü, DM ve senaryo sınır durumları."""
import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

from models import holiday_features, feature_pack, forecast_candidates, inverse_profile, naive_predictions
from forecast_stats import dm_hac, holm_adjust, residual_scenarios

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from fiyat_tahmini import elektrik_fiyatlarini_oku


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads(Path(__file__).with_name('config.json').read_text(encoding='utf-8'))
        cls.prices=elektrik_fiyatlarini_oku(PROJECT)

    def small_config(self):
        c=copy.deepcopy(self.config)
        c['lightgbm']['n_estimators']=4
        c['mean_model']['n_estimators']=4
        c['lear_level_alphas']=[10.]
        c['lear_profile_alphas']=[.01]
        return c

    def test_official_holidays_and_half_days(self):
        t=pd.to_datetime(['2026-03-19 12:00','2026-03-19 13:00','2026-03-20 00:00','2025-06-06 00:00','2024-06-16 00:00','2026-10-28 12:00','2026-10-28 13:00'])
        result=holiday_features(t,self.config)
        self.assertEqual(result['holiday_hour'].tolist(),[0,1,1,1,1,0,1])
        with self.assertRaises(ValueError): holiday_features(pd.to_datetime(['2027-01-01']),self.config)

    def test_feature_cutoff_and_profile_labels(self):
        origin=pd.Timestamp('2026-01-05')
        pack=feature_pack(self.prices,origin,self.config)
        self.assertLess(pack['meta'].loc[pack['train'],'tarih_saat'].max(),pack['cutoff'])
        self.assertTrue(pack['meta'].loc[pack['test'],'daily_actual_mean'].isna().all())
        self.assertEqual(len(pack['target']),48)
        with self.assertRaises(ValueError): feature_pack(self.prices.drop(origin),origin,self.config)

    def test_future_poison_and_delete_do_not_change_forecasts(self):
        c=self.small_config();origin=pd.Timestamp('2026-01-05');cut=origin+pd.Timedelta(hours=24)
        poison=self.prices.copy();poison.loc[poison.index>=cut]=999999.
        a=forecast_candidates(feature_pack(self.prices,origin,c),c)
        b=forecast_candidates(feature_pack(poison,origin,c),c)
        d=forecast_candidates(feature_pack(self.prices.loc[self.prices.index<cut],origin,c),c)
        for name in a[0]:
            np.testing.assert_allclose(a[0][name],b[0][name],rtol=1e-12,atol=1e-9)
            np.testing.assert_allclose(a[0][name],d[0][name],rtol=1e-12,atol=1e-9)
        np.testing.assert_allclose(a[1],b[1])

    def test_profile_uses_predicted_mean_and_zero_fallback(self):
        mean=np.r_[np.repeat(100.,24),np.repeat(200.,24)]
        profile=np.arange(48,dtype=float)
        result=inverse_profile(profile,mean).reshape(2,24)
        np.testing.assert_allclose(result.mean(axis=1),[100,200])
        np.testing.assert_allclose(inverse_profile(np.zeros(48),mean),mean)

    def test_weekend_naive_and_recursive_day_two(self):
        pack=feature_pack(self.prices,pd.Timestamp('2026-01-09'),self.config)
        result=naive_predictions(pack,self.config)
        self.assertTrue((pack['target'].day_of_week>=5).all())
        np.testing.assert_array_equal(result['naive_yesterday_recursive'][:24],result['naive_yesterday_recursive'][24:])
        self.assertTrue(np.isfinite(result['naive_weektype_28d']).all())

    def test_dm_direction_scaling_and_degeneracy(self):
        values=np.arange(1.,35.)
        for lag in (0,3):
            a=dm_hac(values,lag);b=dm_hac(-values,lag);c=dm_hac(values*100,lag)
            self.assertGreater(a['statistic'],0)
            self.assertAlmostEqual(a['statistic'],-b['statistic'])
            self.assertAlmostEqual(a['p_value'],b['p_value'])
            self.assertAlmostEqual(a['statistic'],c['statistic'])
        self.assertEqual(dm_hac(np.zeros(34),3)['p_value'],1)
        self.assertTrue(np.isnan(dm_hac(np.ones(34),3)['p_value']))

    def test_holm_adjustment(self):
        np.testing.assert_allclose(holm_adjust([.01,.04,.03]),[.03,.06,.06])

    def test_scenarios_preserve_known_day_seed_and_paths(self):
        errors=np.stack([np.repeat(10.,48),np.repeat(-10.,48)])
        a,choices=residual_scenarios(np.repeat(100.,48),np.arange(24.),errors,30,42)
        b,_=residual_scenarios(np.repeat(100.,48),np.arange(24.),errors,30,42)
        np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(a[:,:24],np.tile(np.arange(24.),(30,1)))
        np.testing.assert_array_equal(a[:,24:]-100,errors[choices])
        self.assertEqual(a.shape,(30,72))


if __name__=='__main__': unittest.main()
