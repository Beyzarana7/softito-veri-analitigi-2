"""Karar seçimi, havuz-oracle ve sıfır payda sınır durumları."""
import unittest
import numpy as np
from run import score_decision


class DecisionTests(unittest.TestCase):
    def example(self):
        energy=np.zeros((3,72))
        energy[0,24]=1000;energy[1,25]=1000;energy[2,26]=1000
        actual=np.zeros(72);actual[24:27]=[30,10,20]
        forecast=np.zeros(48);forecast[:3]=[30,20,10]
        return energy,np.zeros(3),actual,forecast

    def test_hand_calculated_regret_and_capture(self):
        r,_=score_decision(*self.example(),reference=0)
        self.assertEqual(r['selected'],2);self.assertEqual(r['oracle'],1)
        self.assertEqual(r['regret'],10);self.assertEqual(r['capture'],.5)

    def test_real_future_cannot_change_plan_selection(self):
        energy,fees,actual,forecast=self.example()
        first,_=score_decision(energy,fees,actual,forecast,0)
        changed=actual.copy();changed[24:]=999999
        second,_=score_decision(energy,fees,changed,forecast,0)
        self.assertEqual(first['selected'],second['selected'])
        self.assertEqual(first['expected_cost'],second['expected_cost'])

    def test_no_information_value_is_undefined(self):
        energy,fees,actual,forecast=self.example()
        r,_=score_decision(energy,fees,actual,forecast,reference=1)
        self.assertTrue(np.isnan(r['capture']))

    def test_invalid_input_rejected(self):
        energy,fees,actual,forecast=self.example()
        with self.assertRaises(ValueError): score_decision(energy,fees,actual,forecast[:-1],0)


if __name__=='__main__':unittest.main()
