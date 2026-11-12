"""Fiyat hatası ve karar kalitesini ayrı ölçen yardımcı fonksiyonlar."""
import numpy as np
from scipy.stats import spearmanr


def rank_correlation(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError('Sıralama girdileri sonlu olmalı.')
    if np.ptp(actual) == 0 or np.ptp(predicted) == 0:
        return np.nan
    return float(spearmanr(actual, predicted).statistic)


def weighted_mae(actual, predicted, load):
    actual, predicted, load = map(lambda x: np.asarray(x, dtype=float), (actual, predicted, load))
    if not (actual.shape == predicted.shape == load.shape):
        raise ValueError('Fiyat ve yük boyutları eşleşmiyor.')
    if not all(np.isfinite(x).all() for x in (actual, predicted, load)) or (load < 0).any():
        raise ValueError('Geçersiz fiyat/yük girdisi.')
    if load.sum() == 0:
        return np.nan
    return float(np.average(np.abs(actual - predicted), weights=load))


def cheap_hour_recall(actual, predicted, k):
    """Eşit gerçek fiyatlarda sınırdaki saatlerin payını eşit dağıtır."""
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    if actual.shape != predicted.shape or actual.ndim != 1 or not 1 <= k <= len(actual):
        raise ValueError('Geçersiz en ucuz saat girdisi.')
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError('Fiyatlar sonlu olmalı.')
    selected = np.argsort(predicted, kind='stable')[:k]
    threshold = np.sort(actual)[k - 1]
    strict = actual < threshold
    tied = actual == threshold
    credit = strict.astype(float)
    credit[tied] = (k - strict.sum()) / tied.sum()
    true_selected = np.argsort(actual, kind='stable')[:k]
    deterministic = len(set(selected) & set(true_selected)) / k
    return float(credit[selected].sum() / k), deterministic


def information_capture(reference, selected, oracle, tolerance=0.02):
    denominator = reference - oracle
    if denominator < -tolerance:
        raise ValueError('Havuz minimumu referanstan pahalı olamaz.')
    return float((reference - selected) / denominator) if denominator > tolerance else np.nan


def paired_bootstrap(differences, repetitions, confidence, seed, block_length=1):
    """Aynı haftaların A−B farklarını birlikte örnekleyerek ortalama fark CI üretir."""
    delta = np.asarray(differences, float)
    n = len(delta)
    if n < 2 or not np.isfinite(delta).all() or not 1 <= block_length <= n:
        raise ValueError('Bootstrap için geçerli eşleştirilmiş haftalar gerekli.')
    rng = np.random.default_rng(seed)
    if block_length == 1:
        indices = rng.integers(0, n, size=(repetitions, n))
    else:
        # Örtüşen, dairesel olmayan ardışık bloklar; son blok n haftaya kırpılır.
        starts = rng.integers(0, n - block_length + 1, size=(repetitions, int(np.ceil(n / block_length))))
        indices = (starts[..., None] + np.arange(block_length)).reshape(repetitions, -1)[:, :n]
    means = delta[indices].mean(axis=1)
    alpha = (1 - confidence) / 2
    low, high = np.quantile(means, [alpha, 1 - alpha])
    return float(delta.mean()), float(low), float(high)
