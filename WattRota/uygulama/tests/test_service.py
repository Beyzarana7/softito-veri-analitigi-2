import unittest,sys,json,hashlib,os
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service import available_through,published_at,build_planning_prices,evaluate_saved,check_connection,SOURCE_PROJECT
class ServiceTests(unittest.TestCase):
    def test_publication_boundary(self):
        self.assertEqual(available_through('2025-10-05 13:59'),pd.Timestamp('2025-10-06'))
        self.assertEqual(available_through('2025-10-05 14:00'),pd.Timestamp('2025-10-07'))
        index=pd.date_range('2025-10-06',periods=72,freq='h')
        self.assertEqual(sum(published_at(index)<=pd.Timestamp('2025-10-05 13:59')),0)
        self.assertEqual(sum(published_at(index)<=pd.Timestamp('2025-10-05 14:00')),24)
        self.assertEqual(sum(published_at(index)<=pd.Timestamp('2025-10-06 14:00')),48)
    def test_future_input_rejected(self):
        series=pd.Series([3000.],index=pd.DatetimeIndex(['2025-10-07']))
        with self.assertRaisesRegex(ValueError,'Gelecek fiyatı'):
            build_planning_prices(series,pd.date_range('2025-10-06',periods=72,freq='h'),'2025-10-05 15:00')
    def test_existing_model_horizon_guard(self):
        series=pd.Series([3000.],index=pd.DatetimeIndex(['2025-10-05 23:00']))
        with self.assertRaisesRegex(ValueError,'48 saatlik'):
            build_planning_prices(series,pd.date_range('2025-10-06',periods=72,freq='h'),'2025-10-05 13:00')
    def test_copied_sources_are_unchanged(self):
        for f in (ROOT/'legacy').rglob('*'):
            if f.is_file():self.assertEqual(hashlib.sha256(f.read_bytes()).digest(),hashlib.sha256((SOURCE_PROJECT/f.relative_to(ROOT/'legacy')).read_bytes()).digest())
    def test_missing_actuals_never_show_savings(self):
        folder=sorted(p for p in (ROOT/'runs').iterdir() if p.is_dir() and (p/'result.json').exists())[0]
        before={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['decision.json','prices.csv','plan.csv']}
        result=evaluate_saved(folder,None,'2025-10-05 16:00')
        self.assertEqual(result['status'],'Henüz değerlendirilemedi');self.assertIsNone(result['actual_advantage_tl'])
        for name,h in before.items():self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),h)
    @unittest.skipUnless((SOURCE_PROJECT/".env").exists() or all(os.environ.get(k) for k in ("DB_HOST","DB_PORT","DB_NAME","DB_USER","DB_PASSWORD")), "PostgreSQL yerel yapılandırması yok")
    def test_postgresql_real_connection(self):
        self.assertTrue(check_connection()['connected'])
    def test_saved_actual_plan(self):
        folder=sorted(p for p in (ROOT/'runs').iterdir() if p.is_dir() and (p/'result.json').exists())[0]
        result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        self.assertTrue(result['success']);self.assertTrue(result['decision']['independent_validation'])
        self.assertEqual(result['decision']['solver']['kisit_sayisi'],8637)
        self.assertEqual(len(pd.read_csv(folder/'prices.csv')),72)
        self.assertEqual(result['evaluation']['status'],'Değerlendirildi')
if __name__=='__main__':unittest.main(verbosity=2)
