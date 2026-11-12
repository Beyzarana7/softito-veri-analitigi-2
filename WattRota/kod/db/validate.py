"""CSV/PostgreSQL eşdeğerliği, sonuç yükleme ve veri sözlüğü entegrasyon kontrolü."""
from datetime import datetime, timezone, timedelta
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import highspy
import pandas as pd
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError

from .engine import create_db_engine, db_transaction, ConfigurationError, DatabaseError
from .readers import read_firm, read_prices
from .results import (ensure_results_schema, prepare_result_rows, upsert_result_rows,
                      result_counts, forecast_log, weekly, methods, savings)
from .dictionary import export_dictionary


def assert_env_ignored(project):
    if subprocess.run(['git','check-ignore','--quiet','.env'],cwd=project).returncode!=0:
        raise ConfigurationError('.env Git tarafından dışlanmıyor; işlem durduruldu.')
    tracked=subprocess.check_output(['git','ls-files','--','.env','notebooks/.env'],cwd=project)
    if tracked:
        raise ConfigurationError('.env izlenen dosyalar arasında; işlem durduruldu.')


def bounded_solve(firm,seed):
    from firma_cizelgeleme import firma_cizelgele
    real_highs=highspy.Highs
    def deterministic_highs():
        solver=real_highs()
        solver.setOptionValue('mip_max_nodes',1)
        return solver
    # Yalnız entegrasyon testinde: aynı deterministik arama bütçesi, zaman kesiminden kaçınma.
    with patch.object(highspy,'Highs',new=deterministic_highs):
        result=firma_cizelgele(firm,zaman_siniri=300,goreli_acik=.001,
                              yerel_iyilestirme=False,baslangic_cozumu=seed)
    if result[-1]['durum']=='Time limit reached':
        raise AssertionError('Düğüm bütçesinden önce zaman sınırı doldu; deterministik eşdeğerlik testi geçerli değil.')
    return result


def verify_forecast_append_only(engine):
    # Test kaydı ve bütün denemeler dış işlemin sonunda geri alınır; canlı kayıt oluşturulmaz.
    with engine.connect() as conn:
        transaction=conn.begin()
        try:
            generated=datetime(2025,10,6,tzinfo=timezone.utc)
            conn.execute(insert(forecast_log).values(generated_at=generated,target_time=generated+timedelta(days=1),
                                                    method='__integration_test__',prediction=123.))
            for statement in ('UPDATE results.forecast_log SET prediction=124 WHERE method=\'__integration_test__\'',
                              'DELETE FROM results.forecast_log WHERE method=\'__integration_test__\'',
                              'TRUNCATE results.forecast_log'):
                savepoint=conn.begin_nested()
                blocked=False
                try:
                    conn.execute(text(statement))
                except DBAPIError as error:
                    blocked=getattr(error.orig,'sqlstate',None)=='55000'
                finally:
                    savepoint.rollback()
                if not blocked:
                    raise AssertionError('forecast_log değişiklik engeli doğrulanamadı.')
        finally:
            transaction.rollback()


def validate(project,output=None):
    assert_env_ignored(project)
    sys.path.insert(0,str(project/'src'))
    from firma_cizelgeleme import firma_verisini_oku, maliyet_ve_ozet
    from fiyat_tahmini import elektrik_fiyatlarini_oku
    from firma_verisi import firma_planini_dogrula
    engine=create_db_engine(project)
    if output is None:
        output=project/'data/results/postgresql_06'
        if output.exists():
            output=project/('data/results/postgresql_06_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    else:
        output=Path(output).resolve()
    if output.exists():
        raise FileExistsError('Entegrasyon sonuç klasörü zaten var; yeni çalışma için ayrı yol gerekir.')
    try:
        csv= firma_verisini_oku(project)
        sql= read_firm(engine)
        for name in csv:
            pd.testing.assert_frame_equal(csv[name],sql[name],check_exact=True)
        print('18 firma tablosu: tip, sıra ve değerler birebir eşleşti.',flush=True)
        csv_price=elektrik_fiyatlarini_oku(project);sql_price=read_prices(engine)
        pd.testing.assert_series_equal(csv_price,sql_price,check_exact=True,check_freq=False)
        if len(sql_price)!=24984 or csv_price.sum()!=sql_price.sum():
            raise AssertionError('Fiyat sayısı/toplamı eşleşmiyor.')
        price_check=dict(rows=len(sql_price),sum_tl_mwh=float(sql_price.sum()),
                         first=str(sql_price.index.min()),last=str(sql_price.index.max()),exact=True)
        ref_csv=maliyet_ve_ozet(csv,csv['referans_plan'],csv['referans_yuklemeler'])
        ref_sql=maliyet_ve_ozet(sql,sql['referans_plan'],sql['referans_yuklemeler'])
        for a,b in zip(ref_csv,ref_sql):
            if isinstance(a,pd.Series):pd.testing.assert_series_equal(a,b,check_exact=True)
            else:pd.testing.assert_frame_equal(a,b,check_exact=True)
        seed_folder=project/'data/results/firma_01_cizelgeleme'
        plan=pd.read_csv(seed_folder/'onerilen_plan.csv',keep_default_na=False)
        loads=pd.read_csv(seed_folder/'onerilen_yuklemeler.csv')
        for df in (plan,loads):df['tarih_saat']=pd.to_datetime(df['tarih_saat'])
        seed=(plan,loads)
        print('CSV tam firma modeli, sabit düğüm bütçesiyle çözülüyor.',flush=True)
        solved_csv=bounded_solve(csv,seed)
        print('PostgreSQL tam firma modeli, aynı bütçeyle çözülüyor.',flush=True)
        solved_sql=bounded_solve(sql,seed)
        for a,b in zip(solved_csv[:6],solved_sql[:6]):
            if isinstance(a,pd.Series):pd.testing.assert_series_equal(a,b,check_exact=True)
            else:pd.testing.assert_frame_equal(a,b,check_exact=True)
        for firm,solved in ((csv,solved_csv),(sql,solved_sql)):
            firma_planini_dogrula(firm,solved[0],solved[1])
        metric='Karşılaştırılan toplam maliyet (TL)'
        equality=dict(reference_cost_tl=float(ref_csv[-1][metric]),optimized_cost_tl=float(solved_csv[5][metric]),
                      exact_inputs=True,exact_reference_cost=True,exact_optimized_cost=True,
                      exact_selected_plan=True,exact_loading_plan=True,exact_validator_outputs=True,
                      solver_status_csv=solved_csv[-1]['durum'],solver_status_postgresql=solved_sql[-1]['durum'],
                      solver_node_limit=1,solver_threads=1,solver_seed=42,
                      csv_gap=solved_csv[-1]['goreli_acik'],postgresql_gap=solved_sql[-1]['goreli_acik'],
                      csv_bound_tl=solved_csv[-1]['alt_sinir_tl'],postgresql_bound_tl=solved_sql[-1]['alt_sinir_tl'])
        print('İki bağımsız çözümün plan, maliyet ve doğrulayıcı çıktıları birebir eşleşti.',flush=True)
        batches,source_hashes=prepare_result_rows(project)
        ensure_results_schema(engine)
        upsert_result_rows(engine,batches)
        first=result_counts(engine)
        # İçeriğin de değişmediğini kontrol et; yalnız satır sayısını kontrol etmek yeterli değil.
        def snapshots():
            with db_transaction(engine) as conn:
                return {table.name:[dict(r) for r in conn.execute(select(table).order_by(*list(table.primary_key))).mappings()]
                        for table in (weekly,methods,savings)}
        before=snapshots()
        upsert_result_rows(engine,batches)
        second=result_counts(engine)
        if first!=second or before!=snapshots():
            raise AssertionError('İdempotent yükleme kontrolü başarısız.')
        with db_transaction(engine) as conn:
            for table,rows in batches:
                for row in rows:
                    match=conn.execute(select(table).where(*[table.c[c.name]==row[c.name] for c in table.primary_key])).mappings().one()
                    for key,value in row.items():
                        if match[key]!=value:raise AssertionError('SQL sonuç değeri CSV ile eşleşmiyor: '+table.name+'.'+key)
        verify_forecast_append_only(engine)
        if result_counts(engine)['forecast_log']!=first['forecast_log']:
            raise AssertionError('Geçici forecast test kaydı geri alınmadı.')
        dictionary=project/'veri/veri_sozlugu_taslak.md'
        table_count=export_dictionary(engine,dictionary)
        output.mkdir(parents=True)
        solved_csv[0].to_csv(output/'selected_plan.csv',index=False,encoding='utf-8-sig')
        solved_csv[1].to_csv(output/'selected_loads.csv',index=False,encoding='utf-8-sig')
        info=dict(price=price_check,equivalence=equality,results_counts=second,
                  results_idempotent=True,result_values_equal_csv=True,forecast_update_delete_truncate_blocked=True,
                  live_forecast_connected=False,base_schema_tables=table_count,locked_test_evaluated=False,
                  result_sources_sha256=source_hashes,env_gitignored=True)
        (output/'validation.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        lines=['# PostgreSQL okuma katmanı — görev 6','',
               'CSV akışı değişmedi. Yeni SQLAlchemy katmanı `kod/db/` altındadır. Bağlantı değerleri yalnız proje kökündeki Git dışı `.env` dosyasından okunur; URL ve değerler raporlanmaz.','',
               f"18 firma tablosunun tip, satır sırası ve değerleri birebir eşleşti. Fiyat serisi {price_check['rows']} satır; toplam {price_check['sum_tl_mwh']}; ilk {price_check['first']}; son {price_check['last']}.",'',
               f"Referans maliyeti: {equality['reference_cost_tl']:.5f} TL. Testte bulunan öneri maliyeti: {equality['optimized_cost_tl']:.5f} TL. Her iki yoldan seçilen üretim/yükleme planı ve bağımsız doğrulayıcının bütün çıktıları birebir eşleşti.",
               'Çözücü karşılaştırması sabit seed, tek iş parçacığı, bir arama düğümü ve aynı doğrulanmış başlangıçla iki kez bağımsız çalıştırıldı. Normal süre sınırlı çalışmalarda aynı plan garantisi verilmez. Test planı kesin optimum iddiası değildir; gap ve alt sınırlar validation.json içinde saklanır.','',
               f"Sonuç tabloları: {json.dumps(second,ensure_ascii=False)}. İki yüklemede kayıt sayıları ve içerikler değişmedi; SQL değerleri kaynak CSV kayıtlarıyla karşılaştırıldı.",
               '`results.forecast_log` yalnız şema olarak oluşturuldu. UPDATE, DELETE ve TRUNCATE engelleri geri alınan test işlemiyle doğrulandı; test kaydı kalıcılaştırılmadı. Canlı akış bağlanmadı. Bu engelleri veritabanı sahibi/süper kullanıcı kaldırabilir; yöneticiye karşı değişmez kayıt garantisi değildir.','',
               'Yalnız 34 geliştirme haftası ve 2025 firma karşılaştırması sonuç tablolarına yüklendi. Kilitli 10 hafta açılmadı. 20 temel tablonun sözlüğü `veri/veri_sozlugu_taslak.md` dosyasına katalogdan çıkarıldı.']
        (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print(json.dumps(info,ensure_ascii=True),flush=True)
        return info
    finally:
        engine.dispose()


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Yeni entegrasyon sonuç klasörü; mevcut klasöre yazılmaz.')
    args=parser.parse_args()
    try:
        validate(Path(__file__).resolve().parents[2],args.output)
    except (ConfigurationError,DatabaseError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
    except DBAPIError:
        print('Veritabanı kontrolü tamamlanamadı; bağlantı ayrıntıları gizlendi.',file=sys.stderr);raise SystemExit(1)
