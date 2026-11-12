"""Optimizasyon başlatmayan mevcut ve yeni kontrollerin sınırlı koşucusu."""
from pathlib import Path
import sys,unittest,json,io,warnings
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
warnings.filterwarnings('ignore')
names=['test_user_input','test_service','test_analytics','test_input_ui','test_engineering','test_final_fixes','test_simple_ui']
report={};ok=True
for name in names:
    stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromName(name)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    report[name]={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
    print(name,report[name],flush=True)
    if not result.wasSuccessful():print(stream.getvalue(),flush=True);ok=False
out={'date':'2026-11-12','optimization_started':False,'suites':report,'passed':ok,'test_count':sum(x['run'] for x in report.values())}
(ROOT/'tests/final_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
sys.exit(0 if ok else 1)
