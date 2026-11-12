import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest

import highspy
import numpy as np

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
from instrumentation import Recorder
from full_run import recover_fatal_week,write_json,process_active


class FullTests(unittest.TestCase):
    def test_physical_formulation_is_unchanged(self):
        def body(path):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='solve')
            cut=next(i for i,n in enumerate(f.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='solver' for t in n.targets))
            return ast.dump(ast.Module(body=f.body[:cut],type_ignores=[]),include_attributes=False)
        self.assertEqual(body(PROJECT/'experiments/04_direct_milp_60s/solver.py'),body(HERE/'instrumented_solver.py'))

    def test_callback_and_warm_start_api(self):
        with tempfile.TemporaryDirectory() as temp:
            rec=Recorder(Path(temp));s=highspy.Highs()
            s.setOptionValue('output_flag',True);s.setOptionValue('log_to_console',False)
            s.setOptionValue('log_file',str(Path(temp)/'solver_trace.txt'))
            s.setOptionValue('threads',1);s.setOptionValue('random_seed',42);s.setOptionValue('time_limit',1.)
            lp=highspy.HighsLp();lp.num_col_=2;lp.num_row_=1
            lp.col_cost_=[-1.,-1.];lp.col_lower_=[0.,0.];lp.col_upper_=[1.,1.]
            lp.row_lower_=[-highspy.kHighsInf];lp.row_upper_=[1.5]
            lp.integrality_=[highspy.HighsVarType.kInteger]*2
            lp.a_matrix_.format_=highspy.MatrixFormat.kColwise
            lp.a_matrix_.start_=[0,1,2];lp.a_matrix_.index_=[0,0];lp.a_matrix_.value_=[1.,1.]
            rec.attach(s);rec.options_at(s,'before_model');self.assertEqual(s.passModel(lp),highspy.HighsStatus.kOk)
            rec.options_at(s,'after_model')
            status=s.setSolution(2,np.array([0,1],dtype=np.int32),np.array([0.,0.]))
            rec.api_status('setSolution',status);self.assertEqual(status,highspy.HighsStatus.kOk)
            rec.options_at(s,'before_run');s.run();rec.options_at(s,'after_run');rec.final(s);rec.finish()
            data=rec.summary();self.assertFalse(data['callback_errors'])
            for stage in ('before_model','after_model','before_run','after_run'):
                self.assertEqual(data['options'][stage]['random_seed']['value'],42)
            self.assertTrue((Path(temp)/'solver_trace.txt').exists())
            self.assertTrue((Path(temp)/'solver_events.jsonl').exists())
            self.assertGreater(data['event_counts']['mip_solution'],0)
            del s

    def test_fatal_week_preserves_successes_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'oracle').mkdir()
            write_json(folder/'oracle/run.json',dict(week='2026-01-05',run_key='oracle',actual_cost_tl=10.))
            write_json(folder/'oracle/attempt.json',dict(week='2026-01-05',run_key='oracle',attempt=1,state='success'))
            recovered=recover_fatal_week(folder,'2026-01-05',dict(reason='test'))
            self.assertEqual(len(recovered['success']),1)
            self.assertEqual(len(recovered['attempts']),10)
            self.assertEqual(sum(r['state']=='blocked_week_fatal' for r in recovered['attempts']),9)

    def test_running_process_is_detected(self):
        import os
        self.assertTrue(process_active(os.getpid()))

    def test_active_process_prevents_second_runner(self):
        import os
        from full_run import main
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);write_json(out/'process.json',dict(pid=os.getpid()))
            with self.assertRaisesRegex(ValueError,'halen çalışıyor'):
                main(PROJECT,out,HERE/'config.json',resume=True)

    def test_report_keeps_failed_runs_visible(self):
        import pandas as pd
        from full_report import report
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            write_json(out/'completion.json',dict(experiment_id='unit',elapsed_seconds=1.,weeks_processed=34,weeks_complete=0,successful_milp=0))
            pd.DataFrame([dict(week='2026-01-05',run_key='oracle',state='failed',reason='unit failure')]).to_csv(out/'run_attempts.csv',index=False)
            report(out)
            self.assertIn('unit failure',(out/'report.md').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main(verbosity=2)
