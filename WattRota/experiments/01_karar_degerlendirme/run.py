"""Kayıtlı tahminlerin karar odaklı değerlendirmesi; mevcut deneylere yazmaz."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from metrics import (cheap_hour_recall, information_capture, paired_bootstrap,
                     rank_correlation, weighted_mae)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(project, output, config_file):
    config = json.loads(config_file.read_text(encoding='utf-8'))
    if output.exists():
        raise FileExistsError('Çıktı klasörü zaten var; yeni bir klasör seçin.')
    sys.path.insert(0, str(project / 'src'))
    from firma_cizelgeleme import firma_verisini_oku, maliyet_ve_ozet
    from fiyat_tahmini import elektrik_fiyatlarini_oku
    from ortak_plan_karsilastirmasi import arsivden_plan, tarihleri_tasi

    pool = project / 'data/results/ortak_plan_deneyi'
    forecast_path = project / 'data/results/tahmin_gelistirme/saatlik_tahminler.csv'
    files = [forecast_path, pool / 'plan_indeksi.csv', pool / 'saatlik_enerji.npy',
             pool / 'ortak_planlar.zip', pool / 'haftalik_kararlar.csv', config_file]
    files += list((project / 'data/raw/epias').glob('Piyasa_Takas_Fiyati-*.csv'))
    files += list((project / 'data/synthetic/firma_01').glob('*.csv'))
    files += list((project / 'src').glob('*.py'))
    files += [project / 'data/results/firma_01_veri_kontrolu' / f'{n}.csv'
              for n in ('referans_plan', 'referans_yuklemeler')]
    hashes = {str(p.resolve()): digest(p) for p in files}
    # Kayıtlı sonuçların kaynak izleri güncel dosyalarla uyuşmuyorsa eski deneyi kullanma.
    manifest = json.loads((project / 'data/results/tahmin_gelistirme/deney_izleri.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        if digest(project / name) != expected:
            raise ValueError(f'Kayıtlı deney kaynağı değişmiş: {name}')

    forecasts = pd.read_csv(forecast_path, parse_dates=['karar_zamani', 'tarih_saat'])
    forecasts = forecasts.loc[forecasts['bolum'].eq(config['section']) & forecasts['model'].isin(config['models'])].copy()
    if forecasts.duplicated(['model', 'karar_zamani', 'tarih_saat']).any():
        raise ValueError('Tekrarlanan tahmin var.')
    index = pd.read_csv(pool / 'plan_indeksi.csv')
    energy = np.load(pool / 'saatlik_enerji.npy')
    fees = index['elektrik_disi_gider_tl'].to_numpy()
    if energy.shape != (len(index), 72) or not np.isfinite(energy).all() or (energy < 0).any():
        raise ValueError('Geçersiz plan enerji matrisi.')
    ref_matches = index.index[(index['diger_kaynaklar'] == 'referans') &
                              (index['H02_kaynagi'] == 'referans') &
                              (index['yukleme_kaynagi'] == 'referans')]
    if len(ref_matches) != 1:
        raise ValueError('Tek bir referans plan gerekli.')
    ref = int(ref_matches[0])
    firm = firma_verisini_oku(project)
    base_start = firm['tesis_takvimi']['tarih_saat'].min()
    prices = elektrik_fiyatlarini_oku(project)
    saved = pd.read_csv(pool / 'haftalik_kararlar.csv', parse_dates=['karar_zamani']).set_index(['karar_zamani', 'model'])
    records = []
    physical_checks = 0
    for week, frame in forecasts.groupby('karar_zamani', sort=True):
        times = pd.date_range(week, periods=72, freq='h')
        actual = prices.reindex(times).to_numpy()
        if not np.isfinite(actual).all() or set(frame['model']) != set(config['models']):
            raise ValueError('Hafta veya fiyat kapsamı eksik.')
        costs = energy @ actual / 1000 + fees
        oracle = int(np.argmin(costs))
        v = tarihleri_tasi(firm, week)
        v['fiyatlar'] = pd.DataFrame({'tarih_saat': times, 'PTF (TL/MWh)': actual})
        validated = {}
        for model in config['models']:
            f = frame.loc[frame['model'].eq(model)].sort_values('tarih_saat')
            if not pd.DatetimeIndex(f['tarih_saat']).equals(times[24:]):
                raise ValueError('Tahmin ufku 48 saat olmalı.')
            predicted = f['tahmin'].to_numpy()
            if not np.isfinite(predicted).all() or (predicted < 0).any():
                raise ValueError('Geçersiz tahmin.')
            np.testing.assert_allclose(f['gercek'], actual[24:], atol=0.000001, rtol=0)
            expected_costs = energy @ np.r_[actual[:24], predicted] / 1000 + fees
            selected = int(np.argmin(expected_costs))
            pid = index.iloc[selected]['plan_id']
            prior = saved.loc[(week, model)]
            if prior['secilen_plan'] != pid:
                raise ValueError('Yeniden hesaplanan seçim kayıtlı deneyle eşleşmedi.')
            np.testing.assert_allclose(prior['gercek_maliyet_tl'], costs[selected], atol=0.02, rtol=0)
            # Her haftada seçilen, referans ve havuz-oracle planlar bağımsız denetlenir.
            for position in {ref, oracle, selected}:
                if position not in validated:
                    p, y = arsivden_plan(pool, index.iloc[position]['plan_id'], week, base_start)
                    summary = maliyet_ve_ozet(v, p, y)[-1]
                    np.testing.assert_allclose(summary['Karşılaştırılan toplam maliyet (TL)'], costs[position], atol=0.02, rtol=0)
                    validated[position] = True
                    physical_checks += 1
            daily = [cheap_hour_recall(actual[24 + 24*d:48 + 24*d], predicted[24*d:24 + 24*d], config['cheap_k_per_day']) for d in range(2)]
            rec = dict(karar_zamani=week, model=model, secilen_plan=pid,
                       havuz_oracle_plan=index.iloc[oracle]['plan_id'], referans_maliyet_tl=costs[ref],
                       tahminli_gercek_maliyet_tl=costs[selected], havuz_oracle_maliyet_tl=costs[oracle],
                       havuz_regret_tl=costs[selected] - costs[oracle],
                       referansa_avantaj_tl=costs[ref] - costs[selected],
                       havuz_bilgi_degeri_tl=costs[ref] - costs[oracle],
                       bilgi_degeri_yakalama=information_capture(costs[ref], costs[selected], costs[oracle], config['information_value_minimum_tl']),
                       mae_tl_mwh=np.abs(actual[24:] - predicted).mean(),
                       referans_yuk_agirlikli_mae=weighted_mae(actual[24:], predicted, energy[ref, 24:]),
                       secilen_yuk_agirlikli_mae=weighted_mae(actual[24:], predicted, energy[selected, 24:]),
                       fiyat_spearman_48s=rank_correlation(actual[24:], predicted),
                       plan_maliyeti_spearman=rank_correlation(costs, expected_costs),
                       ucuz_k_saat_orani=np.mean([x[0] for x in daily]),
                       ucuz_k_saat_deterministik=np.mean([x[1] for x in daily]),
                       bagimsiz_kontrol=True)
            records.append(rec)
        print(f'Doğrulandı: {week.date()}', flush=True)

    weekly = pd.DataFrame(records).sort_values(['karar_zamani', 'model'])
    if weekly.empty:
        raise ValueError('Haftalık değerlendirme boş.')
    summary = weekly.groupby('model', sort=False).agg(
        hafta_sayisi=('karar_zamani', 'nunique'), ortalama_maliyet_tl=('tahminli_gercek_maliyet_tl', 'mean'),
        ortalama_regret_tl=('havuz_regret_tl', 'mean'), ortalama_avantaj_tl=('referansa_avantaj_tl', 'mean'),
        bilgi_degeri_yakalama_ortalama=('bilgi_degeri_yakalama', 'mean'),
        bilgi_degeri_tanimli_hafta=('bilgi_degeri_yakalama', 'count'),
        mae=('mae_tl_mwh', 'mean'), yuk_agirlikli_mae=('referans_yuk_agirlikli_mae', 'mean'),
        secilen_yuk_agirlikli_mae=('secilen_yuk_agirlikli_mae', 'mean'),
        fiyat_spearman=('fiyat_spearman_48s', 'mean'), fiyat_spearman_tanimli_hafta=('fiyat_spearman_48s', 'count'),
        plan_spearman=('plan_maliyeti_spearman', 'mean'),
        ucuz_k_saat_orani=('ucuz_k_saat_orani', 'mean'))
    for model in summary.index:
        subset = weekly.loc[weekly['model'].eq(model)]
        denom = subset['havuz_bilgi_degeri_tl'].sum()
        summary.loc[model, 'toplam_bilgi_degeri_yakalama'] = subset['referansa_avantaj_tl'].sum() / denom if denom > config['information_value_minimum_tl'] else np.nan
    pivot = weekly.pivot(index='karar_zamani', columns='model', values='tahminli_gercek_maliyet_tl').sort_index()
    if pivot.isna().any().any():
        raise ValueError('Bootstrap için haftalar eşleşmiyor.')
    comparisons = []
    for a, b in itertools.combinations(config['models'], 2):
        delta = (pivot[a] - pivot[b]).to_numpy()
        for length in (1, config['block_length_weeks']):
            mean, low, high = paired_bootstrap(delta, config['bootstrap_repetitions'], config['confidence_level'], config['seed'], length)
            comparisons.append(dict(model_a=a, model_b=b, fark_tanimi='A eksi B; negatif A daha ucuz',
                                    yontem='paired_iid' if length == 1 else 'paired_moving_block',
                                    blok_hafta=length, hafta_sayisi=len(delta), ortalama_fark_tl=mean,
                                    ci95_alt_tl=low, ci95_ust_tl=high,
                                    a_daha_ucuz_hafta=int((delta < -0.02).sum()),
                                    esit_hafta=int((np.abs(delta) <= 0.02).sum()),
                                    b_daha_ucuz_hafta=int((delta > 0.02).sum())))
    ci = pd.DataFrame(comparisons)
    for name, before in hashes.items():
        if digest(Path(name)) != before:
            raise ValueError('Çalışma sırasında girdi değişti: ' + name)
    output.mkdir(parents=True)
    weekly.to_csv(output / 'haftalik_metrikler.csv', index=False, encoding='utf-8-sig')
    summary.to_csv(output / 'model_ozeti.csv', encoding='utf-8-sig')
    ci.to_csv(output / 'eslestirilmis_bootstrap.csv', index=False, encoding='utf-8-sig')
    plot_results(weekly, summary, ci, output)
    source_files = list(Path(__file__).parent.glob('*.py')) + [config_file]
    input_manifest = {str(Path(name).relative_to(project)) if Path(name).is_relative_to(project) else 'evaluation_config.json': value
                      for name, value in hashes.items()}
    metadata = dict(config=config, scope=config['scope'], weekly_full_milp_oracle_available=False,
                    period_start=str(pivot.index.min()), period_end=str(pivot.index.max()),
                    weeks=len(pivot), plans=len(index), independent_plan_checks=physical_checks,
                    retrospectively_seen_2026=True, input_sha256=input_manifest,
                    evaluation_source_sha256={p.name: digest(p) for p in source_files})
    (output / 'deney_bilgisi.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    write_report(summary, ci, metadata, output)
    print(summary.round(4).to_string(), flush=True)
    print(ci.round(4).to_string(index=False), flush=True)


def plot_results(weekly, summary, ci, output):
    labels = {'son_yayinlanan_gun': 'Basit', 'random_forest_365gun': 'İlk ML', 'hgb_duzeltme_365': 'Geliştirilmiş ML'}
    s = summary.reindex(list(labels))
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    fields = [('ortalama_regret_tl', 'Havuz regret (TL/hafta)'),
              ('toplam_bilgi_degeri_yakalama', 'Toplam bilgi değeri yakalama oranı'),
              ('yuk_agirlikli_mae', 'Referans yük ağırlıklı MAE (TL/MWh)'),
              ('fiyat_spearman', 'Fiyat sıralaması — Spearman'),
              ('plan_spearman', 'Plan maliyeti sıralaması — Spearman'),
              ('ucuz_k_saat_orani', 'Günlük en ucuz 6 saat — eşit fiyat düzeltmeli')]
    for ax, (column, title) in zip(axes.flat, fields):
        ax.bar(list(labels.values()), s[column], color=['#64748b', '#0e7490', '#c76b26'])
        ax.set_title(title, fontsize=10)
        ax.tick_params(axis='x', labelsize=8)
        ax.grid(axis='y', alpha=0.2)
    fig.suptitle('2026 — 44 tarihsel hafta, aynı 19 plan\nHavuz minimumu tam MILP oracle değildir', fontsize=12)
    fig.tight_layout()
    for ext in ('png', 'pdf'):
        fig.savefig(output / f'metrik_karsilastirmasi.{ext}', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4))
    for model, frame in weekly.groupby('model'):
        ax.plot(frame['karar_zamani'], frame['havuz_regret_tl'], label=labels[model], alpha=0.8)
    ax.set(ylabel='Havuz regret (TL)', title='Haftalık karar kaybı — tarihsel değerlendirme')
    ax.legend(); ax.grid(alpha=0.2); fig.tight_layout()
    fig.savefig(output / 'haftalik_regret.png', dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4))
    comparison_labels = []
    for i, row in ci.iterrows():
        name = f"{labels[row['model_a']]} − {labels[row['model_b']]} / " + ('IID' if row['blok_hafta'] == 1 else '4 hafta blok')
        ax.plot([row['ci95_alt_tl'], row['ci95_ust_tl']], [i, i], color='#0e7490', linewidth=2)
        ax.scatter(row['ortalama_fark_tl'], i, color='#c76b26')
        comparison_labels.append(name)
    ax.set_yticks(range(len(ci)), comparison_labels, fontsize=9)
    ax.axvline(0, color='black', linestyle='--', alpha=0.5)
    ax.set(xlabel='Ortalama haftalık maliyet farkı (TL), %95 bootstrap aralığı', title='Eşleştirilmiş karşılaştırma — negatif değer ilk yöntem lehine')
    fig.tight_layout(); fig.savefig(output / 'bootstrap_guven_araliklari.png', dpi=160); plt.close(fig)


def write_report(summary, ci, metadata, output):
    lines = ['# Karar odaklı değerlendirme', '',
             f"Dönem: {metadata['period_start'][:10]}–{metadata['period_end'][:10]}; {metadata['weeks']} haftalık karar, {metadata['plans']} aday plan.", '',
             '## Kapsam ve tanımlar', '',
             '- Bu çalışma mevcut tahminleri yeniden değerlendirir; yeni model eğitmez. 2026 dönemi önceden görülmüştür.',
             '- Oracle yerine **havuz-oracle** kullanılır: aynı 19 geçerli planın gerçekleşmiş fiyatlarla en ucuzu. Tam MILP oracle maliyeti değildir; tam çözüm uzayındaki regret ve bilgi yakalama oranı burada hesaplanmış sayılmaz.',
             '- Havuz regret = seçilen planın gerçekleşmiş maliyeti − havuz-oracle maliyeti. Bilgi değeri yakalama = (referans − seçilen)/(referans − havuz-oracle). Payda 0,02 TL veya altındaysa oran tanımsızdır; 0 yazılmaz. Negatif oranlar kırpılmaz.',
             '- Saatlik fiyat metrikleri yalnız tahmin edilen 48 saati kapsar. Yük ağırlıklı MAE = Σ(yük × mutlak fiyat hatası)/Σyük; kWh/kWh ağırlıklarıyla sonuç TL/MWh olur. Birincil ağırlık sabit referans yüküdür; seçilen plan yükü ayrıca raporlanır.',
             '- Spearman: 48 saatlik fiyat sıralaması ve ayrıca 19 planın maliyet sıralaması. Sabit dizide korelasyon tanımsız bırakılır.',
             '- En ucuz k: iki hedef günün her birinde k=6. Tahmin eşitlikleri saat sırasıyla çözülür; gerçek fiyatın k sınırındaki eşitliklere kesirli kredi dağıtılır. Saat sırasına göre deterministik örtüşme de ayrı sütundadır.',
             '- Haftalık oranların ortalaması ile toplam kazanç/toplam bilgi değeri ayrı raporlanır. Küçük pozitif paydalı bir haftadaki kayıp, haftalık oran ortalamasını çok negatif yapabilir. Toplam oran bu küçük paydalara eşit ağırlık vermez; iki değer aynı ölçü değildir.',
             '- Bootstrap aynı haftaların A−B maliyet farklarını birlikte örnekler; 10.000 tekrar ve seed=42 kullanılır. IID varsayımına ek olarak ardışık 4 haftalık hareketli blok duyarlılığı gösterilir. Aralıklar bu retrospektif örneklemin belirsizliğidir; gelecek kazanç garantisi veya çoklu test düzeltilmiş anlamlılık sonucu değildir.', '',
             '## Model özeti', '',
             '| Yöntem | Regret TL/hafta | Toplam bilgi yakalama | Yük ağırlıklı MAE | Fiyat Spearman | Ucuz 6 saat oranı |',
             '|---|---:|---:|---:|---:|---:|']
    for model, r in summary.iterrows():
        lines.append(f"| {model} | {r['ortalama_regret_tl']:.2f} | {r['toplam_bilgi_degeri_yakalama']:.3f} | {r['yuk_agirlikli_mae']:.2f} | {r['fiyat_spearman']:.3f} | {r['ucuz_k_saat_orani']:.3f} |")
    lines += ['', '## Eşleştirilmiş maliyet farkları', '', '| A − B | Bootstrap | Ortalama TL/hafta | %95 aralık |', '|---|---|---:|---|']
    for _, r in ci.iterrows():
        lines.append(f"| {r['model_a']} − {r['model_b']} | {r['yontem']} | {r['ortalama_fark_tl']:.2f} | [{r['ci95_alt_tl']:.2f}, {r['ci95_ust_tl']:.2f}] |")
    lines += ['', '## Doğrulama', '',
              f"Her haftanın referans, havuz-oracle ve seçilen planları bağımsız fiziksel/maliyet doğrulamasından geçirildi ({metadata['independent_plan_checks']} benzersiz hafta-plan kontrolü). Matris maliyetleri ve seçimler kayıtlı deneyle karşılaştırıldı. Girdi dosyalarının çalışma öncesi ve sonrası SHA-256 özetleri eşleşti.", '',
              'Haftalık tam-MILP oracle serisi mevcut olmadığından bu kapsamın dışındaki oracle/regret sonuçları üretilmedi. Üç ayrı tarihsel MILP örneği 44 haftaya genellenmedi.']
    (output / 'rapor.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    args = parser.parse_args()
    evaluate(args.project.resolve(), args.output.resolve(), args.config.resolve())
