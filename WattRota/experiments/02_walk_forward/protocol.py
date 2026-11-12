"""Sabit test ayrımı ve genişleyen pencereli, bilgi kesimli walk-forward protokolü."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from threadpoolctl import threadpool_limits


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_config(config):
    if (config['known_hours'], config['forecast_hours'], config['plan_hours']) != (24, 48, 72):
        raise ValueError('Bu firma protokolü 24 bilinen + 48 tahmin = 72 saat içindir.')
    if config['decision_frequency'] != 'W-MON' or config['locked_test_weeks'] < 1:
        raise ValueError('Haftalık pazartesi protokolü ve pozitif kilitli hafta sayısı gerekli.')
    if config['selection_metric'] != 'mae_tl_mwh' or config['selection_tie_break'] != 'model_id_ascending':
        raise ValueError('Desteklenmeyen seçim kuralı.')
    ids = [m['id'] for m in config['models']]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Model kimlikleri benzersiz olmalı.')
    if any(m['kind'] not in ('naive', 'rf', 'hgb') for m in config['models']):
        raise ValueError('Desteklenmeyen model türü.')
    if any(m['kind'] == 'naive' and m['parameters'] for m in config['models']):
        raise ValueError('Naive yöntem ek parametre almaz.')
    if any(k in m['parameters'] for m in config['models'] for k in ('random_state', 'n_jobs')):
        raise ValueError('Seed ve iş parçacığı sayısı yalnız ortak config alanlarından alınır.')
    if config['threads'] < 1 or config['minimum_training_rows'] < 1:
        raise ValueError('Geçersiz eğitim ayarı.')
    if config['feature_builders'] != {'rf': 'fiyat_tahmini.ozellikleri_hazirla', 'hgb': 'fiyat_tahmini_gelistirme.karar_ornekleri'}:
        raise ValueError('Özellik üretici sürümü desteklenmiyor.')


def build_folds(prices, config):
    validate_config(config)
    if prices.empty or prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError('Fiyat dizisi sıralı ve benzersiz olmalı.')
    if not prices.index.equals(pd.date_range(prices.index.min(), prices.index.max(), freq='h')):
        raise ValueError('Saatlik seri kesintisiz olmalı.')
    year = config['evaluation_year']
    snapshot_end = pd.Timestamp(config['evaluation_snapshot_end'])
    if snapshot_end > prices.index.max():
        raise ValueError('Config içindeki veri kesim tarihi mevcut değil.')
    decisions = pd.date_range(f'{year}-01-01', f'{year}-12-31', freq=config['decision_frequency'])
    complete = [d for d in decisions if d >= prices.index.min() and d + pd.Timedelta(hours=config['plan_hours'] - 1) <= snapshot_end]
    n_test = config['locked_test_weeks']
    if len(complete) <= n_test:
        raise ValueError('Geliştirme ve kilitli test ayrımı için yeterli hafta yok.')
    records = []
    for i, d in enumerate(complete):
        cut = d + pd.Timedelta(hours=config['known_hours'])
        records.append(dict(fold_id=i, decision_origin=d,
                            known_last=cut - pd.Timedelta(hours=1),
                            target_start=cut, target_end=d + pd.Timedelta(hours=config['plan_hours'] - 1),
                            split='locked_test' if i >= len(complete) - n_test else 'development',
                            history_start=pd.Timestamp(config['history_start'])))
    folds = pd.DataFrame(records)
    first_locked = folds.loc[folds['split'].eq('locked_test'), 'decision_origin'].min()
    if not (folds.loc[folds['split'].eq('development'), 'target_end'] < first_locked).all():
        raise ValueError('Geliştirme hedefleri kilitli bölümle çakışıyor.')
    return folds


def source_fingerprint(project, config_file):
    own = Path(__file__).parent
    files = [own / n for n in ('protocol.py', 'run.py')]
    files += [project / 'src' / f'{n}.py' for n in ('fiyat_tahmini', 'fiyat_tahmini_gelistirme')]
    files += [project / 'requirements.txt']
    files += list((project / 'data/raw/epias').glob('Piyasa_Takas_Fiyati-*.csv'))
    return dict(config_sha256=sha256(config_file),
                files={str(p.relative_to(project)): sha256(p) for p in files})


def create_lock(project, config_file, output, prices):
    if output.exists():
        raise FileExistsError('Protokol klasörü zaten var; kilit üzerine yazılmaz.')
    config = json.loads(config_file.read_text(encoding='utf-8'))
    folds = build_folds(prices, config)
    fingerprint = source_fingerprint(project, config_file)
    locked = folds.loc[folds['split'].eq('locked_test')]
    payload = dict(protocol_version=config['protocol_version'], **fingerprint,
                   development_weeks=int(folds['split'].eq('development').sum()),
                   locked_test_weeks=len(locked),
                   locked_origins=[str(x) for x in locked['decision_origin']],
                   interpretation=config['interpretation'],
                   test_evaluated_at_lock_creation=False,
                   test_policy='No selection or tuning on locked outcomes; sequential refits may use only labels available at each origin.')
    output.mkdir(parents=True)
    folds.to_csv(output / 'folds.csv', index=False, encoding='utf-8-sig')
    payload['folds_sha256'] = sha256(output / 'folds.csv')
    (output / 'config_snapshot.json').write_bytes(config_file.read_bytes())
    (output / 'test_lock.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return folds, payload


def verify_lock(project, config_file, output):
    payload = json.loads((output / 'test_lock.json').read_text(encoding='utf-8'))
    current = source_fingerprint(project, config_file)
    if current['config_sha256'] != payload['config_sha256'] or current['files'] != payload['files']:
        raise ValueError('Config, kaynak veya ham veri kilitten sonra değişti; bu protokol yeniden kullanılamaz.')
    if sha256(output / 'config_snapshot.json') != payload['config_sha256'] or sha256(output / 'folds.csv') != payload['folds_sha256']:
        raise ValueError('Kilitli protokol çıktısı değiştirilmiş.')
    folds = pd.read_csv(output / 'folds.csv', parse_dates=['decision_origin', 'known_last', 'target_start', 'target_end', 'history_start'])
    return folds, payload


def predict_expanding(prices, origin, model_spec, config, project):
    """Hiçbir modele tahmin başlangıcı veya sonrasındaki fiyatları vermez."""
    validate_config(config)
    sys.path.insert(0, str(project / 'src'))
    from fiyat_tahmini import ozellikleri_hazirla
    from fiyat_tahmini_gelistirme import karar_ornekleri
    origin = pd.Timestamp(origin)
    if origin != origin.normalize():
        raise ValueError('Karar başlangıcı 00.00 olmalı.')
    cutoff = origin + pd.Timedelta(hours=config['known_hours'])
    start = pd.Timestamp(config['history_start'])
    known = prices.loc[(prices.index >= start) & (prices.index < cutoff)].copy()
    if known.empty or known.index.min() != start or known.index.max() != cutoff - pd.Timedelta(hours=1):
        raise ValueError('Eğitim başlangıcı veya açıklanmış ilk gün eksik.')
    if not known.index.equals(pd.date_range(start, known.index.max(), freq='h')):
        raise ValueError('Bilinen geçmiş kesintisiz olmalı.')
    if not np.isfinite(known).all() or (known < 0).any():
        raise ValueError('Geçersiz bilinen fiyat.')
    target = pd.date_range(cutoff, periods=config['forecast_hours'], freq='h')
    kind, params = model_spec['kind'], dict(model_spec['parameters'])
    info = dict(model=model_spec['id'], decision_origin=str(origin),
                available_last=str(known.index.max()), history_start=str(start),
                training_strategy='expanding', training_rows=0,
                training_target_start=None, training_target_end=None,
                seed=config['seed'])
    if kind == 'naive':
        prediction = np.tile(known.reindex(pd.date_range(origin, periods=24, freq='h')).to_numpy(), 2)
    elif kind == 'rf':
        features = ozellikleri_hazirla(known, target.max())
        train = features.loc[features.index < cutoff].dropna()
        test = features.reindex(target)
        if len(train) < config['minimum_training_rows'] or test.isna().any().any():
            raise ValueError('RF eğitim veya özellik geçmişi yetersiz.')
        labels = known.reindex(train.index)
        regressor = RandomForestRegressor(random_state=config['seed'], n_jobs=config['threads'], **params)
        with threadpool_limits(limits=config['threads']):
            regressor.fit(train, labels)
            prediction = regressor.predict(test)
        info.update(training_rows=len(train), training_target_start=str(train.index.min()),
                    training_target_end=str(train.index.max()), feature_count=len(train.columns))
    else:
        features, meta = karar_ornekleri(known, target.max())
        train_mask = (meta['tarih_saat'] < cutoff) & meta['gercek'].notna() & features.notna().all(axis=1)
        test_mask = meta['karar_zamani'].eq(origin)
        train, test = features.loc[train_mask], features.loc[test_mask]
        if len(train) < config['minimum_training_rows'] or len(test) != config['forecast_hours'] or test.isna().any().any():
            raise ValueError('HGB eğitim veya özellik geçmişi yetersiz.')
        if not pd.DatetimeIndex(meta.loc[test_mask, 'tarih_saat']).equals(target):
            raise ValueError('HGB hedef saatleri uyuşmuyor.')
        labels = meta.loc[train_mask, 'gercek'] - train['aciklanmis_ayni_saat']
        regressor = HistGradientBoostingRegressor(random_state=config['seed'], **params)
        with threadpool_limits(limits=config['threads']):
            regressor.fit(train, labels)
            prediction = test['aciklanmis_ayni_saat'].to_numpy() + regressor.predict(test)
        info.update(training_rows=len(train), training_target_start=str(meta.loc[train_mask, 'tarih_saat'].min()),
                    training_target_end=str(meta.loc[train_mask, 'tarih_saat'].max()), feature_count=len(train.columns))
    prediction = np.maximum(np.asarray(prediction, float), config['prediction_floor'])
    if prediction.shape != (config['forecast_hours'],) or not np.isfinite(prediction).all():
        raise ValueError('Geçersiz tahmin çıktısı.')
    if info['training_target_end'] is not None and pd.Timestamp(info['training_target_end']) >= cutoff:
        raise ValueError('Eğitim hedefi tahmin dönemine sızıyor.')
    return pd.Series(prediction, index=target, name='prediction'), info


def select_model(predictions, folds, allowed_models):
    development = folds.loc[folds['split'].eq('development'), 'decision_origin']
    if not set(pd.to_datetime(predictions['decision_origin'])).issubset(set(development)):
        raise ValueError('Model seçimine kilitli test veya tanımsız hafta verilemez.')
    if set(predictions['model']) != set(allowed_models):
        raise ValueError('Aday modeller eksik veya tanımsız.')
    for model, frame in predictions.groupby('model'):
        if set(pd.to_datetime(frame['decision_origin'])) != set(development):
            raise ValueError('Model seçimi bütün geliştirme haftalarını kullanmalı.')
        if frame.duplicated(['decision_origin', 'target_time']).any() or not frame.groupby('decision_origin').size().eq(48).all():
            raise ValueError('Model seçimi için her haftada 48 benzersiz hedef gerekli.')
        for origin, week in frame.groupby('decision_origin'):
            expected = pd.date_range(pd.Timestamp(origin) + pd.Timedelta(hours=24), periods=48, freq='h')
            if not pd.DatetimeIndex(pd.to_datetime(week['target_time']).sort_values()).equals(expected):
                raise ValueError('Model seçiminin hedef saatleri fold tanımıyla uyuşmuyor.')
    error = (predictions['prediction'] - predictions['actual']).abs()
    if not np.isfinite(error).all():
        raise ValueError('Model seçiminde eksik/geçersiz sonuç var.')
    scores = predictions.assign(absolute_error=error).groupby('model')['absolute_error'].mean().rename('mae_tl_mwh').reset_index()
    return scores.sort_values(['mae_tl_mwh', 'model']).reset_index(drop=True)
