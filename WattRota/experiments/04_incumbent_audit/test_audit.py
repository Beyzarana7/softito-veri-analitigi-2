import copy
import unittest
import numpy as np
from scipy.sparse import csc_matrix
from model_audit import evaluate,assert_same_model,tightened_regret


class AuditTests(unittest.TestCase):
    def matrix(self):
        return dict(A=csc_matrix([[1.,1.]]),c=np.array([2.,3.]),lo=np.array([0.,0.]),hi=np.array([1.,1.]),
           lb=np.array([1.]),ub=np.array([1.]),integer=np.array([True,True]),warm=np.array([1.,0.]),
           sabit_bedel=5.,etiket=['one_activity'],adlar=['x','y'])
    def test_valid_and_objective(self):
        r=evaluate(self.matrix(),7.)
        self.assertTrue(r['full_model_feasible']);self.assertEqual(r['rows_checked'],1)
    def test_constraint_and_integrality(self):
        m=self.matrix();m['warm']=np.array([.5,0.])
        r=evaluate(m,6.)
        self.assertEqual({v['kind'] for v in r['violations']},{'constraint','integrality'})
    def test_accounting_error(self):
        self.assertEqual(evaluate(self.matrix(),8.)['violations'][0]['kind'],'objective_accounting')
    def test_model_difference_rejected(self):
        a=self.matrix();b=copy.deepcopy(a);b['hi'][0]=2.
        with self.assertRaises(AssertionError):assert_same_model(a,b)
    def test_tighter_upper_raises_regret_lower(self):
        self.assertEqual(tightened_regret(100,70,90),(10.,30.))
        self.assertEqual(tightened_regret(100,70,80),(20.,30.))


if __name__=='__main__':unittest.main(verbosity=2)
