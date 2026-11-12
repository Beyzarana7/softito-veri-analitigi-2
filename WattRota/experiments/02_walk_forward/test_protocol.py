"""Zaman ayrımı, kilit, genişleyen eğitim ve gelecek-veri sızıntısı kontrolleri."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

from protocol import build_folds, create_lock, verify_lock, predict_expanding, select_model

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from fiyat_tahmini import elektrik_fiyatlarini_oku


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(Path(__file__).with_name('config.json').read_text(encoding='utf-8'))
        cls.prices = elektrik_fiyatlarini_oku(PROJECT)
        cls.folds = build_folds(cls.prices, cls.config)

    def test_split_is_34_plus_10_without_partial_week(self):
        self.assertEqual(self.folds['split'].value_counts().to_dict(), {'development': 34, 'locked_test': 10})
        locked = self.folds.loc[self.folds['split'].eq('locked_test')]
        self.assertEqual(locked['decision_origin'].min(), pd.Timestamp('2026-08-31'))
        self.assertEqual(locked['decision_origin'].max(), pd.Timestamp('2026-11-02'))
        self.assertEqual(locked['target_end'].max(), pd.Timestamp('2026-11-04 23:00'))
        self.assertLess(self.folds.loc[self.folds['split'].eq('development'), 'target_end'].max(), locked['decision_origin'].min())

    def test_lock_detects_config_changes_and_will_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            cfg = temp / 'config.json'
            cfg.write_text(json.dumps(self.config), encoding='utf-8')
            output = temp / 'protocol'
            create_lock(PROJECT, cfg, output, self.prices)
            verify_lock(PROJECT, cfg, output)
            with self.assertRaises(FileExistsError):
                create_lock(PROJECT, cfg, output, self.prices)
            cfg.write_text(json.dumps(dict(self.config, seed=43)), encoding='utf-8')
            with self.assertRaises(ValueError):
                verify_lock(PROJECT, cfg, output)

    def test_new_prices_do_not_move_locked_dates(self):
        extra = pd.Series(1000., index=pd.date_range(self.prices.index.max() + pd.Timedelta(hours=1), '2026-12-31 23:00', freq='h'))
        new = build_folds(pd.concat([self.prices, extra]), self.config)
        pd.testing.assert_frame_equal(self.folds, new)

    def test_lock_detects_fold_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            cfg = temp / 'config.json'
            cfg.write_text(json.dumps(self.config), encoding='utf-8')
            output = temp / 'protocol'
            create_lock(PROJECT, cfg, output, self.prices)
            with (output / 'folds.csv').open('a', encoding='utf-8') as stream:
                stream.write('\n')
            with self.assertRaises(ValueError):
                verify_lock(PROJECT, cfg, output)

    def small_config(self):
        # Birim testleri eğitim mantığını küçük modellerle sınar; performans raporu üretmez.
        cfg = copy.deepcopy(self.config)
        for model in cfg['models']:
            if model['kind'] == 'rf':
                model['parameters']['n_estimators'] = 4
                model['parameters']['max_depth'] = 4
            if model['kind'] == 'hgb':
                model['parameters']['max_iter'] = 5
        return cfg

    def test_future_poison_deletion_and_seed_reproducibility(self):
        cfg = self.small_config()
        origin = self.folds.iloc[0]['decision_origin']
        cutoff = origin + pd.Timedelta(hours=24)
        poison = self.prices.copy()
        poison.loc[poison.index >= cutoff] = 999999.0
        for spec in cfg['models']:
            a, _ = predict_expanding(self.prices, origin, spec, cfg, PROJECT)
            b, _ = predict_expanding(poison, origin, spec, cfg, PROJECT)
            c, _ = predict_expanding(self.prices.loc[self.prices.index < cutoff], origin, spec, cfg, PROJECT)
            pd.testing.assert_series_equal(a, b)
            pd.testing.assert_series_equal(a, c)

    def test_training_expands_and_labels_stay_before_forecast(self):
        cfg = self.small_config()
        first, later = self.folds.iloc[0], self.folds.iloc[1]
        for spec in [s for s in cfg['models'] if s['kind'] != 'naive']:
            _, a = predict_expanding(self.prices, first['decision_origin'], spec, cfg, PROJECT)
            _, b = predict_expanding(self.prices, later['decision_origin'], spec, cfg, PROJECT)
            self.assertEqual(a['training_target_start'], b['training_target_start'])
            self.assertGreater(b['training_rows'], a['training_rows'])
            self.assertLess(pd.Timestamp(b['training_target_end']), later['target_start'])

    def test_missing_known_hour_rejected(self):
        origin = self.folds.iloc[0]['decision_origin']
        with self.assertRaises(ValueError):
            predict_expanding(self.prices.drop(origin), origin, self.config['models'][0], self.config, PROJECT)

    def selection_frame(self):
        records = []
        for _, fold in self.folds.loc[self.folds['split'].eq('development')].iterrows():
            for model in self.config['models']:
                for time in pd.date_range(fold['target_start'], periods=48, freq='h'):
                    records.append(dict(decision_origin=fold['decision_origin'], target_time=time,
                                        model=model['id'], prediction=1., actual=1.))
        return pd.DataFrame(records)

    def test_selection_refuses_locked_week(self):
        predictions = self.selection_frame()
        scores = select_model(predictions, self.folds, [s['id'] for s in self.config['models']])
        self.assertEqual(scores.iloc[0]['model'], sorted(s['id'] for s in self.config['models'])[0])
        predictions.loc[0, 'decision_origin'] = self.folds.loc[self.folds['split'].eq('locked_test'), 'decision_origin'].min()
        with self.assertRaises(ValueError):
            select_model(predictions, self.folds, [s['id'] for s in self.config['models']])

    def test_selection_refuses_missing_model_or_week(self):
        predictions = self.selection_frame()
        ids = [s['id'] for s in self.config['models']]
        with self.assertRaises(ValueError):
            select_model(predictions.loc[predictions['model'].ne(ids[0])], self.folds, ids)
        with self.assertRaises(ValueError):
            select_model(predictions.iloc[48:], self.folds, ids)

    def test_locked_runner_requires_explicit_flag(self):
        from run import run
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            cfg = temp / 'config.json'
            cfg.write_text(json.dumps(self.config), encoding='utf-8')
            output = temp / 'protocol'
            create_lock(PROJECT, cfg, output, self.prices)
            with self.assertRaises(ValueError):
                run(PROJECT, output, cfg, 'locked-test', confirm_locked_test=False)
            self.assertFalse((output / 'locked_test').exists())


if __name__ == '__main__':
    unittest.main()
