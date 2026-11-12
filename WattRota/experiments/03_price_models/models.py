"""48 saatlik fiyat tahmini: takvim, saat/ufuk bazlı Lasso-AR ve LightGBM."""
import warnings

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import Lasso
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


def holiday_features(times, config):
    times = pd.DatetimeIndex(times)
    full, half = set(), set()
    for year, holidays in config['religious_holidays'].items():
        for month_day in config['national_holidays_month_day']:
            full.add(pd.Timestamp(f'{year}-{month_day}'))
        half.add(pd.Timestamp(f'{year}-10-28'))
        for key, days in [('ramadan_start', 3), ('sacrifice_start', 4)]:
            start = pd.Timestamp(holidays[key])
            full.update(pd.date_range(start, periods=days, freq='D'))
            half.add(start - pd.Timedelta(days=1))
    if not set(times.year).issubset(set(map(int, config['religious_holidays']))):
        raise ValueError('Resmî tarih kaynağı olmayan yıl için takvim üretilemez.')
    day = times.normalize()
    result = pd.DataFrame(index=pd.RangeIndex(len(times)))
    result['holiday_full_day'] = day.isin(full).astype(float)
    result['holiday_half_day'] = day.isin(half).astype(float)
    result['holiday_hour'] = (day.isin(full) | (day.isin(half) & (times.hour >= config['holiday_half_day_hour']))).astype(float)
    result['day_before_holiday'] = (day + pd.Timedelta(days=1)).isin(full).astype(float)
    result['day_after_holiday'] = (day - pd.Timedelta(days=1)).isin(full).astype(float)
    return result


def feature_pack(known, origin, config):
    from fiyat_tahmini_gelistirme import karar_ornekleri
    origin = pd.Timestamp(origin)
    cutoff = origin + pd.Timedelta(hours=config['known_hours'])
    known = known.loc[(known.index >= pd.Timestamp(config['history_start'])) & (known.index < cutoff)].copy()
    expected = pd.date_range(config['history_start'], cutoff - pd.Timedelta(hours=1), freq='h')
    if not known.index.equals(expected) or not np.isfinite(known).all() or (known < 0).any():
        raise ValueError('Bilinen fiyat geçmişi eksik, sırasız veya geçersiz.')
    target = pd.date_range(cutoff, periods=config['forecast_hours'], freq='h')
    x, meta = karar_ornekleri(known, target.max())
    target_times = pd.DatetimeIndex(meta['tarih_saat'])
    decision_times = pd.DatetimeIndex(meta['karar_zamani'])
    x = pd.concat([x, holiday_features(target_times, config)], axis=1)
    for hour in range(24):
        x[f'announced_hour_{hour}'] = known.reindex(decision_times + pd.Timedelta(hours=hour)).to_numpy()
        x[f'hour_is_{hour}'] = (target_times.hour == hour).astype(float)
    for weekday in range(7):
        x[f'weekday_is_{weekday}'] = (target_times.day_of_week == weekday).astype(float)
    daily_mean = known.groupby(known.index.normalize()).mean()
    meta['target_day'] = target_times.normalize()
    meta['daily_actual_mean'] = daily_mean.reindex(target_times.normalize()).to_numpy()
    train = (meta['tarih_saat'] < cutoff) & meta['gercek'].notna() & x.notna().all(axis=1)
    test = meta['karar_zamani'].eq(origin)
    if train.sum() < config['minimum_training_rows'] or test.sum() != 48 or x.loc[test].isna().any().any():
        raise ValueError('Eğitim veya tahmin özellikleri eksik.')
    if not pd.DatetimeIndex(meta.loc[test, 'tarih_saat']).equals(target):
        raise ValueError('48 saatlik hedef uyuşmuyor.')
    return dict(x=x, meta=meta, train=train, test=test, target=target, known=known,
                origin=origin, cutoff=cutoff)


def lgb(config, mean=False, classification=False):
    parameters = dict(config['mean_model'] if mean else config['lightgbm'])
    cls = LGBMClassifier if classification else LGBMRegressor
    parameters['objective'] = 'binary' if classification else 'regression_l1'
    return cls(random_state=config['seed'], n_jobs=config['threads'], **parameters)


def naive_predictions(pack, config):
    known, origin, target = pack['known'], pack['origin'], pack['target']
    # İkinci bilinmeyen günde gerçek dünkü fiyat yoktur: son açıklanmış gün profili özyinelemeli tekrarlanır.
    yesterday = np.tile(known.reindex(pd.date_range(origin, periods=24, freq='h')).to_numpy(), 2)
    previous_week = known.reindex(target - pd.Timedelta(days=7)).to_numpy()
    type_naive = []
    for time in target:
        days = pd.date_range(origin - pd.Timedelta(days=config['weekday_naive_lookback_days'] - 1), origin, freq='D')
        days = days[(days.day_of_week >= 5) == (time.day_of_week >= 5)]
        past = known.reindex(days + pd.Timedelta(hours=time.hour)).dropna()
        if past.empty:
            raise ValueError('Hafta içi/sonu naive için geçmiş yok.')
        type_naive.append(past.mean())
    return {'naive_yesterday_recursive': yesterday, 'naive_previous_week': previous_week,
            'naive_weektype_28d': np.asarray(type_naive)}


def predicted_daily_means(pack, config):
    x, m, train, test = pack['x'], pack['meta'], pack['train'], pack['test']
    columns = ['hedef_gun', 'hedef_ay', 'ufuk_gun', 'aciklanmis_gun_mean', 'aciklanmis_gun_min',
               'aciklanmis_gun_max', 'aciklanmis_gun_std', 'holiday_full_day', 'holiday_half_day',
               'day_before_holiday', 'day_after_holiday']
    keys = pd.MultiIndex.from_frame(m[['karar_zamani', 'target_day']])
    unique = ~keys.duplicated()
    fit_rows = train & unique
    test_rows = test & unique
    model = lgb(config, mean=True)
    model.fit(x.loc[fit_rows, columns], m.loc[fit_rows, 'daily_actual_mean'])
    daily = np.maximum(model.predict(x.loc[test_rows, columns]), 0)
    days = pd.DatetimeIndex(m.loc[test_rows, 'target_day'])
    mapping = pd.Series(daily, index=days)
    return mapping.reindex(pd.DatetimeIndex(m.loc[test, 'target_day'])).to_numpy()


def inverse_profile(profile, mean_forecast, epsilon=1e-12):
    profile = np.maximum(np.asarray(profile, float), 0).reshape(2, 24)
    average = profile.mean(axis=1, keepdims=True)
    shape = np.divide(profile, average, out=np.ones_like(profile), where=average > epsilon)
    return shape.reshape(48) * np.asarray(mean_forecast)


def learner(pack, config, target_kind, alpha):
    x, m, train, test = pack['x'], pack['meta'], pack['train'], pack['test']
    y = m['gercek'].copy()
    if target_kind == 'profile':
        y = y / np.maximum(m['daily_actual_mean'], config['profile_mean_epsilon'])
    result = np.empty(48)
    test_indices = x.loc[test].index
    convergence = 0
    # 24 saat x iki gün ufku için ayrı Lasso; ölçekleyici yalnız ilgili eğitim grubunda öğrenilir.
    for pos, row in enumerate(test_indices):
        group = train & m['karar_zamani'].notna() & x['hedef_saat'].eq(x.loc[row, 'hedef_saat']) & x['ufuk_gun'].eq(x.loc[row, 'ufuk_gun'])
        if group.sum() < config['lear_minimum_group_rows']:
            raise ValueError('Saat/ufuk Lasso grubu yetersiz.')
        model = make_pipeline(StandardScaler(), Lasso(alpha=alpha, max_iter=config['lear_max_iter'],
                              tol=config['lear_tolerance'], selection='cyclic', random_state=config['seed']))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ConvergenceWarning)
            model.fit(x.loc[group], y.loc[group])
        convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
        result[pos] = model.predict(x.loc[[row]])[0]
    return result, convergence


def forecast_candidates(pack, config):
    x, m, train, test = pack['x'], pack['meta'], pack['train'], pack['test']
    outputs = naive_predictions(pack, config)
    diagnostics = []
    mean_forecast = predicted_daily_means(pack, config)
    with threadpool_limits(limits=config['threads']):
        for kind, alphas in [('level', config['lear_level_alphas']), ('profile', config['lear_profile_alphas'])]:
            for alpha in alphas:
                values, convergence = learner(pack, config, kind, alpha)
                name = f'lear_{kind}_{alpha:g}'
                if kind == 'profile':
                    values = inverse_profile(values, mean_forecast)
                outputs[name] = np.maximum(values, config['prediction_floor'])
                diagnostics.append(dict(model=name, convergence_warnings=convergence))
        level = lgb(config)
        level.fit(x.loc[train], m.loc[train, 'gercek'])
        outputs['lightgbm_level'] = np.maximum(level.predict(x.loc[test]), 0)
        profile = lgb(config)
        shape_y = m.loc[train, 'gercek'] / np.maximum(m.loc[train, 'daily_actual_mean'], config['profile_mean_epsilon'])
        profile.fit(x.loc[train], shape_y)
        outputs['lightgbm_profile'] = inverse_profile(profile.predict(x.loc[test]), mean_forecast)
        zero_y = m.loc[train, 'gercek'].eq(0).astype(int)
        if zero_y.nunique() == 1:
            pzero = np.repeat(float(zero_y.iloc[0]), 48)
        else:
            classifier = lgb(config, classification=True)
            classifier.fit(x.loc[train], zero_y)
            pzero = classifier.predict_proba(x.loc[test])[:, 1]
        positive = train & m['gercek'].gt(0)
        regressor = lgb(config)
        regressor.fit(x.loc[positive], m.loc[positive, 'gercek'])
        positive_price = np.maximum(regressor.predict(x.loc[test]), 0)
        outputs['lightgbm_two_stage'] = np.where(pzero >= config['zero_threshold'], 0., positive_price)
    for name, values in outputs.items():
        if np.asarray(values).shape != (48,) or not np.isfinite(values).all():
            raise ValueError('Geçersiz tahmin: ' + name)
    return outputs, pzero, diagnostics, mean_forecast


def level_only(pack, config):
    model = lgb(config)
    with threadpool_limits(limits=config['threads']):
        model.fit(pack['x'].loc[pack['train']], pack['meta'].loc[pack['train'], 'gercek'])
        return np.maximum(model.predict(pack['x'].loc[pack['test']]), 0)
