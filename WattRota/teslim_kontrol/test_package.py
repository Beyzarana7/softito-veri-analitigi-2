from pathlib import Path
import sys,importlib,json,unittest,io,warnings
R=Path.cwd();sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(R/'uygulama'));sys.path.insert(0,str(R/'uygulama/tests'));warnings.filterwarnings('ignore')
mods=['firma_verisi','firma_cizelgeleme','fiyat_tahmini','service','analytics','engineering','charts','user_input','simple_pages','planning_page']
for m in mods:importlib.import_module(m)
reports={}
for name in ['test_ui_refinement','test_input_session','test_local_integration']:
 out=io.StringIO();r=unittest.TextTestRunner(stream=out).run(unittest.defaultTestLoader.loadTestsFromName(name));reports[name]={'run':r.testsRun,'passed':r.testsRun-len(r.failures)-len(r.errors)-len(r.skipped),'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped)}
 if not r.wasSuccessful():print(out.getvalue())
print(json.dumps({'imports':mods,'tests':reports}))
(R/'teslim_kontrol/ek_testler.json').write_text(json.dumps({'imports':mods,'tests':reports},ensure_ascii=False,indent=2),encoding='utf-8')


sys.exit(1 if any(r["failures"] or r["errors"] for r in reports.values()) else 0)
