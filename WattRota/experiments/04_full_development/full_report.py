"""Sonuçları yalnız mevcut geliştirme deneyinden özetler; solver çağırmaz."""
import json
from pathlib import Path
import numpy as np
import pandas as pd


def table(frame,columns):
    lines=['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    for values in frame[columns].itertuples(index=False,name=None):
        lines.append('| '+' | '.join('tanımsız' if pd.isna(v) else f'{v:.2f}' if isinstance(v,float) else str(v) for v in values)+' |')
    return '\n'.join(lines)


def report(output):
    from metrics import aggregate_capture
    completion=json.loads((output/'completion.json').read_text(encoding='utf-8'))
    def read(name):
        path=output/(name+'.csv')
        return pd.read_csv(path,parse_dates=['week']) if path.exists() else pd.DataFrame()
    weekly=read('weekly_metrics');attempts=read('run_attempts');audit=read('full_model_audit');runs=read('solver_runs');tight=read('tightened_regret')
    summaries=[];comparisons=[]
    if not weekly.empty:
        for policy,frame in weekly.groupby('policy'):
            summaries.append(dict(policy=policy,weeks_with_valid_metrics=len(frame),planned_weeks=34,
                total_actual_cost_tl=float(frame.actual_cost_tl.sum()),total_reference_cost_tl=float(frame.reference_cost_tl.sum()),
                total_savings_tl=float(frame.reference_advantage_tl.sum()),mean_regret_lower_tl=float(frame.regret_lower_tl.mean()),
                mean_regret_upper_tl=float(frame.regret_upper_tl.mean()),
                **aggregate_capture(float(frame.reference_advantage_tl.sum()),float(frame.potential_vs_incumbent_tl.sum()),float(frame.potential_upper_tl.sum()))))
        for week,frame in weekly.groupby('week'):
            f=frame.set_index('policy')
            for mode in ('open','rolling'):
                for source in ('hgb','ensemble'):
                    if source+'_'+mode in f.index and 'naive_'+mode in f.index:
                        a=float(f.loc['naive_'+mode,'actual_cost_tl']);b=float(f.loc[source+'_'+mode,'actual_cost_tl'])
                        comparisons.append(dict(week=week,mode=mode,source=source,naive_cost_tl=a,ml_cost_tl=b,naive_minus_ml_tl=a-b))
    summary=pd.DataFrame(summaries);comparison=pd.DataFrame(comparisons)
    if not summary.empty:summary.to_csv(output/'method_summary.csv',index=False,encoding='utf-8-sig')
    if not comparison.empty:comparison.to_csv(output/'ml_vs_naive.csv',index=False,encoding='utf-8-sig')
    lines=['# WattRota — 34 geliştirme haftası / 60 saniye','',
        f"Deney: {completion['experiment_id']}. Süre: {completion['elapsed_seconds']/60:.2f} dakika. İşlenen hafta: {completion['weeks_processed']}; tam doğrulanmış hafta: {completion['weeks_complete']}/34. Başarılı solver koşumu: {completion['successful_milp']}/340.",'',
        '## Protokol','',
        'Her hafta aynı PostgreSQL firma girdisi, 72 saatlik ufuk ve 18 sipariş kullanıldı. Oracle gerçek fiyatlarla; naive, HGB ve ensemble ilk gün açıklanmış / sonraki iki gün tahmin fiyatıyla çalıştı. D0 açık döngü ve rolling başlangıcıdır; rolling d1/d2 kendi geçmişini koruyarak yeniden çözülür. Yalnız ilk gün uygulanır. Her solve: HiGHS, 60 saniye, seed 42, tek thread, gap hedefi 0,001; yerel arama kapalı. Pilot planları ve başka koşumların iyi sonuçları warm start olarak kullanılmadı.','',
        '## Yöntem sonuçları','']
    if not summary.empty:lines.append(table(summary,['policy','weeks_with_valid_metrics','total_actual_cost_tl','total_savings_tl','mean_regret_lower_tl','mean_regret_upper_tl','capture_vs_incumbent']))
    if not comparison.empty:
        paired=comparison.groupby(['mode','source'],as_index=False).agg(paired_weeks=('week','size'),
             naive_minus_ml_tl=('naive_minus_ml_tl','sum'),weeks_ml_cheaper=('naive_minus_ml_tl',lambda s:int((s>.02).sum())),
             weeks_same_cost=('naive_minus_ml_tl',lambda s:int((s.abs()<=.02).sum())),
             weeks_naive_cheaper=('naive_minus_ml_tl',lambda s:int((s<-.02).sum())))
        lines+=['','## Basit yönteme karşı ML','',table(paired,['mode','source','paired_weeks','naive_minus_ml_tl','weeks_ml_cheaper','weeks_same_cost','weeks_naive_cheaper']),
                '', 'Pozitif naive−ML farkı ML lehine, negatif fark basit yöntem lehinedir. Hafta bazındaki bütün eşleştirmeler ml_vs_naive.csv içindedir. Eksik/başarısız haftalar eşleşmiş sayıya dahil edilmedi; eşleşen hafta sayısı açıkça gösterilir.']
    lines+=['','## Başarısızlıklar ve çözüm kayıtları','']
    if not attempts.empty:
        lines.append(table(attempts.groupby('state',as_index=False).size(),['state','size']))
        failed=attempts.loc[~attempts.state.eq('success')]
        if not failed.empty:lines.append(table(failed.fillna(''),['week','run_key','state','reason']))
    if not runs.empty:
        lines+=[f"Süre sınırına ulaşan: {int(runs.time_limit_reached.sum())}/{len(runs)}. Warm start API kOk sayısı: {int(runs.warm_start_api_status.eq('HighsStatus.kOk').sum())}. MIP solution callback olayı: {int(runs.mip_solution_callback_events.sum())}; improving callback olayı: {int(runs.improving_solution_callback_events.sum())}. Bu sayılar tüm benzersiz uygun çözümlerin sayısı olarak yorumlanmaz."]
    if not audit.empty:lines.append(f"Özgün tam modelde aday uygunluk kontrolü: {int(audit.full_model_feasible.sum())}/{len(audit)}. Birleşik rolling planları gerçekten uygulanmış d0/d1/d2 parçalarından oluşturuldu; bütün model satırları ve amaç eşleşmesi ayrıca kontrol edildi.")
    lines+=['','Native solver_trace.txt ve solver_events.jsonl her koşum klasöründe saklandı. setSolution dönüşü, model aktarımı ve solve öncesi/sonrası etkin seçenekler, primal/dual callback kayıtları, son durum ve sayaçlar solver_diagnostics.json içindedir. Callback/log hatası olan koşum başarısız sayılır; otomatik solver tekrarı yoktur.','',
        '## Oracle ve deney sonrası üst sınır','',
        'Özgün gerçek-fiyatlı oracle koşumu değiştirilmedi. Ayrı best_known_feasible.csv, aynı haftadaki tam modelde doğrulanmış politika ve referans adaylarından en düşük gerçek maliyeti içerir. Bu deney sonrası bir uygun üst sınırdır; bağımsız oracle başarısı veya deploy edilebilir bir yöntem diye sunulmaz. L oracle alt sınırı, U bu uygun maliyet ve C politika maliyeti için regret [max(0,C−U), max(0,C−L)] aralığındadır. Noktasal gerçek regret yalnız mutlak optimum sınırı sertifikalanırsa anlamlıdır.','',
        'Ham oracle regret aralıkları weekly_metrics.csv, sıkılaştırılmış aralıklar tightened_regret.csv içindedir. Bilgi yakalama toplam kazanç / toplam özgün oracle potansiyelidir; sıfır payda tanımsızdır. Deney sonrası politika tabanlı üst sınırdan bağımsız bilgi yakalama oranı türetilmedi.','',
        '## Yorum sınırları','',
        'Rolling–open farkı, yeni açıklanan fiyatlar ile ek çözüm bütçesinin birlikte etkisini içerir. Doğrudan ML katkısı olarak adlandırılamaz. Bu çalışma sabit sentetik firmanın tarihsel fiyat koşullarındaki davranışını ölçer; gerçek tesis genellemesini veya bütün fabrika türlerinde geçerliliği kanıtlamaz. Süre sınırlı çözümler optimum diye sunulmaz. Seed 42 sabittir; seed dayanıklılığı incelenmedi. Geliştirme dönemi daha önce görülmüştür; yeni bağımsız test değildir.','',
        'Kilitli 10 hafta değerlendirilmedi. Seed deneyi, Görev 5 ve stokastik mod başlatılmadı. Pilotlar hash denetimiyle korundu. PostgreSQL yüklemesi aynı deney kimliğiyle iki kez yapılarak idempotans kontrol edildi; solver koşumları tekrarlanmadı.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if not comparison.empty:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,1,figsize=(12,9),layout='constrained')
        s=summary.set_index('policy').total_savings_tl.reindex(['naive_open','hgb_open','ensemble_open','naive_rolling','hgb_rolling','ensemble_rolling'])
        s.plot.barh(ax=axes[0]);axes[0].set(title='34 geliştirme haftası — referansa göre toplam tasarruf',xlabel='TL')
        rolling=comparison.loc[comparison['mode'].eq('rolling')].pivot(index='week',columns='source',values='naive_minus_ml_tl')
        rolling.plot(ax=axes[1],marker='o',markersize=3)
        axes[1].axhline(0,color='black',lw=.8);axes[1].set(title='Rolling: basit yöntem maliyeti − ML maliyeti',ylabel='TL; pozitif ML lehine',xlabel='Hafta')
        fig.savefig(output/'summary.png',dpi=150);plt.close(fig)
    return dict(summary=summaries,ml_comparison=comparisons)
