"""Süre sınırlı gerçek-fiyat MILP benchmark'ını kesin optimumdan ayırır."""
import numpy as np


def decision_metrics(reference,cost,oracle_upper,oracle_lower,tolerance=.02):
    if not np.isfinite([reference,cost,oracle_upper,oracle_lower]).all():
        raise ValueError('Maliyet sınırları sonlu olmalı.')
    if oracle_lower>oracle_upper+tolerance or oracle_upper>reference+tolerance:
        raise ValueError('Oracle maliyet sınırları tutarsız.')
    exact=(oracle_upper-oracle_lower)<=tolerance
    numerator=reference-cost
    denominator=reference-oracle_upper
    return dict(actual_cost_tl=float(cost),reference_advantage_tl=float(numerator),
                oracle_incumbent_gap_tl=float(cost-oracle_upper),
                exact_regret_tl=float(max(0,cost-oracle_upper)) if exact else None,
                regret_lower_tl=float(max(0,cost-oracle_upper)),
                regret_upper_tl=float(max(0,cost-oracle_lower)),
                information_capture_vs_incumbent=float(numerator/denominator) if denominator>tolerance else None,
                potential_vs_incumbent_tl=float(denominator),
                potential_upper_tl=float(reference-oracle_lower),
                oracle_exact_certified=bool(exact),
                beats_oracle_incumbent=bool(cost<oracle_upper-tolerance))


def aggregate_capture(numerator,potential_lower,potential_upper,tolerance=.02):
    empirical=numerator/potential_lower if potential_lower>tolerance else None
    if potential_upper<=tolerance:
        return dict(capture_vs_incumbent=empirical,capture_lower=None,capture_upper=None)
    if potential_lower>tolerance:
        endpoints=[numerator/potential_lower,numerator/potential_upper]
        low,high=min(endpoints),max(endpoints)
        if numerator>=0:high=min(high,1.)
    elif numerator>=0:low=numerator/potential_upper;high=1.
    else:low=None;high=numerator/potential_upper
    return dict(capture_vs_incumbent=empirical,capture_lower=low,capture_upper=high)
