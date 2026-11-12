"""Kilit oluşturma, geliştirme ve ayrı test komutları için deney giriş noktası."""
import argparse
import json
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd
import sklearn

from protocol import create_lock, verify_lock, predict_expanding, select_model, sha256


def run(project, output, config_file, phase, confirm_locked_test=False):
    sys.path.insert(0, str(project / 'src'))
    from fiyat_tahmini import elektrik_fiyatlarini_oku
    config = json.loads(config_file.read_text(encoding='utf-8'))
    prices = elektrik_fiyatlarini_oku(project)
    if phase == 'prepare':
        folds, lock = create_lock(project, config_file, output, prices)
        print(folds.groupby('split')['decision_origin'].agg(['count', 'min', 'max']).to_string(), flush=True)
        return
    folds, lock = verify_lock(project, config_file, output)
    if phase == 'locked-test' and not confirm_locked_test:
        raise ValueError('Kilitli değerlendirme kapalı. Açmak için --confirm-locked-test gerekir.')
    split = 'development' if phase == 'development' else 'locked_test'
    destination = output / split
    if destination.exists():
        raise FileExistsError('Bu bölümün sonuçları zaten var; üzerine yazılmaz.')
    specs = config['models']
    if split == 'locked_test':
        selection_file = output / 'development/model_selection.json'
        seal = json.loads((output / 'development/development_seal.json').read_text(encoding='utf-8'))
        selection = json.loads(selection_file.read_text(encoding='utf-8'))
        if seal['selection_sha256'] != sha256(selection_file) or selection['config_sha256'] != lock['config_sha256'] or seal['test_lock_sha256'] != sha256(output / 'test_lock.json'):
            raise ValueError('Geliştirme seçimi veya kilit değiştirilmiş.')
        for name, value in seal['files'].items():
            if sha256(output / 'development' / name) != value:
                raise ValueError('Geliştirme kaydı değiştirilmiş: ' + name)
        specs = [s for s in specs if s['id'] == selection['selected_model'] or s['kind'] == 'naive']
    np.random.seed(config['seed'])
    rows, audit = [], []
    for _, fold in folds.loc[folds['split'].eq(split)].iterrows():
        origin = fold['decision_origin']
        # Adaptöre yalnız o haftada bilinen veri verilir; puanlama ayrıca yapılır.
        known = prices.loc[prices.index <= fold['known_last']]
        for spec in specs:
            prediction, info = predict_expanding(known, origin, spec, config, project)
            actual = prices.reindex(prediction.index)
            if actual.isna().any():
                raise ValueError('Değerlendirme hedefleri eksik.')
            for time, value in prediction.items():
                rows.append(dict(split=split, decision_origin=origin, target_time=time,
                                 model=spec['id'], prediction=value, actual=actual.loc[time]))
            audit.append(dict(split=split, **info))
        print(f'{split}: {origin.date()} tamamlandı', flush=True)
    verify_lock(project, config_file, output)
    predictions = pd.DataFrame(rows)
    audits = pd.DataFrame(audit)
    for model, frame in audits.loc[audits['training_rows'].gt(0)].groupby('model'):
        if frame['training_target_start'].nunique() != 1 or not frame['training_rows'].is_monotonic_increasing:
            raise ValueError('Genişleyen pencere başlangıcı/satır sayısı tutarsız.')
    if split == 'development':
        scores = select_model(predictions, folds, [m['id'] for m in config['models']])
    else:
        scores = predictions.assign(absolute_error=lambda d: (d['prediction'] - d['actual']).abs()).groupby('model')['absolute_error'].mean().rename('mae_tl_mwh').reset_index()
    destination.mkdir()
    predictions.to_csv(destination / 'predictions.csv', index=False, encoding='utf-8-sig')
    audits.to_csv(destination / 'training_audit.csv', index=False, encoding='utf-8-sig')
    scores.to_csv(destination / 'scores.csv', index=False, encoding='utf-8-sig')
    if split == 'development':
        selection = dict(selected_model=scores.iloc[0]['model'], criterion=config['selection_metric'],
                         selection_split='development_only', config_sha256=lock['config_sha256'],
                         last_selection_target=str(predictions['target_time'].max()),
                         first_locked_origin=lock['locked_origins'][0])
        (destination / 'model_selection.json').write_text(json.dumps(selection, indent=2, ensure_ascii=False), encoding='utf-8')
        seal = dict(selection_sha256=sha256(destination / 'model_selection.json'),
                    test_lock_sha256=sha256(output / 'test_lock.json'),
                    files={p.name: sha256(p) for p in destination.glob('*.csv')})
        (destination / 'development_seal.json').write_text(json.dumps(seal, indent=2), encoding='utf-8')
    metadata = dict(phase=phase, fold_count=predictions['decision_origin'].nunique(),
                    predictions=len(predictions), seed=config['seed'],
                    python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__, sklearn=sklearn.__version__,
                    config_sha256=lock['config_sha256'], test_evaluated=split == 'locked_test',
                    interpretation=config['interpretation'])
    metadata['fold_count'] = int(metadata['fold_count'])
    (destination / 'run_info.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(scores.to_string(index=False), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    parser.add_argument('--phase', choices=['prepare', 'development', 'locked-test'], required=True)
    parser.add_argument('--confirm-locked-test', action='store_true')
    args = parser.parse_args()
    run(args.project.resolve(), args.output.resolve(), args.config.resolve(), args.phase, args.confirm_locked_test)
