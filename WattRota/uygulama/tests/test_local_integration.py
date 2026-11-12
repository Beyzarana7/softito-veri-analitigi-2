from pathlib import Path
import json,hashlib,sys,unittest,subprocess
from unittest.mock import patch,MagicMock
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from service import load_inputs,maliyet_ve_ozet,firma_planini_dogrula,evaluated_cost
from execution import run_worker
class LocalIntegrationTests(unittest.TestCase):
    @unittest.skip("Eski V2 klasörü teslim kapsamı dışında; kaynak bütünlüğü teslim manifestiyle kontrol edilir.")
    def test_v2_unchanged(self):
        v2=ROOT.parent/'wattrota_app_v2'
        baseline=json.loads((ROOT/'v2_koruma.json').read_text(encoding='utf-8'))
        for rel,h in baseline.items():self.assertEqual(hashlib.sha256((v2/rel).read_bytes()).hexdigest(),h,rel)
        for f in (ROOT/'legacy').rglob('*'):
            if f.is_file():self.assertEqual(f.read_bytes(),(v2/f.relative_to(ROOT)).read_bytes())
        self.assertEqual((ROOT/'worker.py').read_bytes(),(v2/'worker.py').read_bytes())
    def test_latest_integrated_plan_and_costs(self):
        candidates=[]
        for f in (ROOT/'runs').glob('*/result.json'):
            r=json.loads(f.read_text(encoding='utf-8'))
            if r['decision'].get('search',{}).get('local_search_enabled'):candidates.append((f,r))
        self.assertEqual(len(candidates),1,'Bu entegrasyon kontrolü yalnız bir yeni buton koşumu üretmeli.')
        f,r=candidates[0];folder=f.parent;v=load_inputs(folder)
        plan=pd.read_csv(folder/'plan.csv',keep_default_na=False);plan.tarih_saat=pd.to_datetime(plan.tarih_saat)
        loads=pd.read_csv(folder/'loads.csv');loads.tarih_saat=pd.to_datetime(loads.tarih_saat)
        firma_planini_dogrula(v,plan,loads)
        expected=maliyet_ve_ozet(v,plan,loads)[-1]['Karşılaştırılan toplam maliyet (TL)']
        self.assertAlmostEqual(expected,r['decision']['expected_cost_tl'],places=5)
        self.assertAlmostEqual(expected,r['decision']['solver']['maliyet_tl'],places=5)
        actual=pd.read_csv(folder/r['evaluation']['price_file'],parse_dates=['tarih_saat']).set_index('tarih_saat').gercek_fiyat_tl_mwh
        cost,_=evaluated_cost(v,plan,loads,actual);ref,_=evaluated_cost(v,v['referans_plan'],v['referans_yuklemeler'],actual)
        self.assertAlmostEqual(cost,r['evaluation']['actual_cost_tl'],places=5)
        self.assertAlmostEqual(ref-cost,r['evaluation']['actual_advantage_tl'],places=5)
        self.assertAlmostEqual(loads.miktar_ton.sum(),6720)
        self.assertFalse(r['decision']['search']['old_solution_loaded'])
    def test_timeout_stops_windows_worker_tree(self):
        p=MagicMock();p.pid=123456;p.communicate.side_effect=[subprocess.TimeoutExpired('test',.01),('','')]
        with patch('execution.subprocess.Popen',return_value=p),patch('execution.subprocess.run') as stop,patch('execution.os.name','nt'):
            with self.assertRaises(subprocess.TimeoutExpired):run_worker(ROOT,timeout=.01)
            self.assertEqual(stop.call_args.args[0],['taskkill','/PID','123456','/T','/F'])
if __name__=='__main__':unittest.main(verbosity=2)
