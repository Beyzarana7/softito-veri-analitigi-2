"""Haftalık kayıp farkları üzerinde DM-HAC ve çoklu karşılaştırma düzeltmesi."""
import numpy as np
from scipy.stats import norm


def dm_hac(differences, lag):
    d = np.asarray(differences, float)
    n = len(d)
    if n < 3 or not np.isfinite(d).all() or not 0 <= lag < n:
        raise ValueError('Geçersiz DM girdisi.')
    centered = d - d.mean()
    variance = centered @ centered / n
    for k in range(1, lag + 1):
        variance += 2 * (1 - k / (lag + 1)) * (centered[k:] @ centered[:-k]) / n
    if variance <= 1e-12:
        return dict(statistic=0. if np.allclose(d, 0) else np.nan,
                    p_value=1. if np.allclose(d, 0) else np.nan, status='zero_variance', mean_difference=float(d.mean()))
    statistic = float(d.mean() / np.sqrt(variance / n))
    return dict(statistic=statistic, p_value=float(2 * norm.sf(abs(statistic))),
                status='ok', mean_difference=float(d.mean()))


def holm_adjust(p_values):
    values = np.asarray(p_values, float)
    adjusted = np.full_like(values, np.nan)
    finite = np.flatnonzero(np.isfinite(values))
    order = finite[np.argsort(values[finite], kind='stable')]
    running = 0.
    for rank, position in enumerate(order):
        running = max(running, (len(order) - rank) * values[position])
        adjusted[position] = min(running, 1.)
    return adjusted


def residual_scenarios(point, known_day, residual_paths, count, seed):
    point, known_day, errors = np.asarray(point, float), np.asarray(known_day, float), np.asarray(residual_paths, float)
    if point.shape != (48,) or known_day.shape != (24,) or errors.ndim != 2 or errors.shape[1] != 48 or not len(errors):
        raise ValueError('Senaryo için 24 bilinen + 48 hedef ve geçmiş 48 saatlik artıklar gerekli.')
    if not all(np.isfinite(x).all() for x in (point, known_day, errors)):
        raise ValueError('Senaryo girdisi sonlu olmalı.')
    rng = np.random.default_rng(seed)
    choices = rng.integers(0, len(errors), count)
    unknown = np.maximum(point + errors[choices], 0)
    return np.c_[np.tile(known_day, (count, 1)), unknown], choices
