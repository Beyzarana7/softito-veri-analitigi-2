"""Single-plan application service. No experiment runners or saved plans are loaded."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import sys, json, hashlib, importlib.util, uuid, traceback, time
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT=Path(__file__).resolve().parent
LEGACY=ROOT/'legacy'
sys.path.insert(0,str(LEGACY));sys.path.insert(0,str(LEGACY/'src'))
from kod.db.engine import create_db_engine, db_transaction
from kod.db.readers import read_table,FIRM_TABLES
from firma_cizelgeleme import firma_cizelgele,maliyet_ve_ozet
from firma_verisi import firma_planini_dogrula

SOURCE_PROJECT=ROOT.parent
PUBLICATION_SOURCE='https://www.epias.com.tr/gun-oncesi-piyasasi/surecler/'
DECISION=pd.Timestamp('2025-10-05 15:00')
def now():return datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()
def save_json(path,obj):
    # Exclusive creation: historical decisions and forecasts cannot be overwritten.
    with Path(path).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False,default=str)
def published_at(hours):return pd.DatetimeIndex(hours).normalize()-pd.Timedelta(days=1)+pd.Timedelta(hours=14)
def available_through(decision):
    d=pd.Timestamp(decision)
    last_day=d.normalize()+pd.Timedelta(days=int(d.hour>=14))
    return last_day+pd.Timedelta(days=1)
def check_connection():
    engine=create_db_engine(SOURCE_PROJECT)
    try:
        with db_transaction(engine) as conn:
            db=conn.execute(text('SELECT current_database()')).scalar_one()
            assert db=='wattrota','Beklenen veritabanı wattrota değil.'
            conn.execute(text('SELECT 1')).scalar_one()
        return {'connected':True,'database':db,'checked_at':now()}
    finally:engine.dispose()
def read_decision_inputs(engine,decision):
    cutoff=available_through(decision)
    with db_transaction(engine) as conn:
        assert conn.execute(text('SELECT current_database()')).scalar_one()=='wattrota'
        # The legacy full firm reader also reads historical future prices. Instead,
        # reuse its typed table reader and deliberately exclude that price table.
        firm={name:read_table(conn,name) for name in FIRM_TABLES if name!='fiyatlar'}
        data=pd.read_sql(text('SELECT tarih_saat,"PTF (TL/MWh)" FROM wattrota.elektrik_fiyatlari WHERE tarih_saat >= :start AND tarih_saat < :cut ORDER BY tarih_saat'),conn,params={'start':'2024-01-01','cut':cutoff.to_pydatetime()})
    history=data.set_index('tarih_saat')['PTF (TL/MWh)'].astype(float)
    history.index=pd.DatetimeIndex(history.index)
    if not history.index.equals(pd.date_range('2024-01-01',cutoff-pd.Timedelta(hours=1),freq='h')):
        raise ValueError('Karar anında açıklanmış fiyat geçmişi eksik veya tekrarlı.')
    if not (published_at(history.index)<=pd.Timestamp(decision)).all():raise ValueError('Bilgi zamanı ihlali.')
    return firm,history
def build_planning_prices(history,index,decision):
    """Adapt the existing 48-hour model to the latest published day, not plan day 1."""
    index=pd.DatetimeIndex(index);decision=pd.Timestamp(decision)
    if len(index)!=72 or not index.equals(pd.date_range(index[0],periods=72,freq='h')):raise ValueError('72 kesintisiz saat gerekli.')
    if index[0]<decision:raise ValueError('Plan başlangıcı karar anından önce olamaz.')
    known_mask=published_at(index)<=decision
    if not (published_at(history.index)<=decision).all():raise ValueError('Gelecek fiyatı tahmin girdisine verilmiş.')
    values=history.reindex(index).where(known_mask)
    audit={'model':'hgb_residual_expanding','training_target_end':None}
    if (~known_mask).any():
        origin=history.index.max().normalize()
        target=pd.date_range(origin+pd.Timedelta(days=1),periods=48,freq='h')
        if not index[~known_mask].isin(target).all():
            raise ValueError('Bu karar anında mevcut modelin 48 saatlik tahmin ufku planı kapsamıyor. Daha ileri ufuk bu sürümde desteklenmiyor; gerçek gelecek fiyat kullanılmadı.')
        spec=importlib.util.spec_from_file_location('wattrota_existing_protocol',LEGACY/'experiments/02_walk_forward/protocol.py')
        protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
        config=json.loads((LEGACY/'experiments/02_walk_forward/config.json').read_text(encoding='utf-8'))
        model=next(m for m in config['models'] if m['id']=='hgb_residual_expanding')
        prediction,audit=protocol.predict_expanding(history,origin,model,config,LEGACY)
        values.loc[index[~known_mask]]=prediction.reindex(index[~known_mask]).to_numpy()
    if values.isna().any() or not np.isfinite(values).all():raise ValueError('Planlama fiyatları eksik.')
    return pd.DataFrame({'tarih_saat':index,'planlama_fiyati_tl_mwh':values.to_numpy(),'aciklanmis':known_mask,'yayin_zamani':published_at(index)}),audit
def evaluated_cost(firm,plan,loads,prices):
    v={k:t.copy(deep=True) for k,t in firm.items()}
    v['fiyatlar']=pd.DataFrame({'tarih_saat':prices.index,'PTF (TL/MWh)':prices.to_numpy()})
    stock,activity,hourly,summary=maliyet_ve_ozet(v,plan,loads)
    return float(summary['Karşılaştırılan toplam maliyet (TL)']),hourly
def evaluate_saved(run_folder,engine,as_of):
    """Read actual prices only after an immutable plan has been saved."""
    folder=Path(run_folder);manifest=json.loads((folder/'decision.json').read_text(encoding='utf-8'))
    index=pd.date_range(manifest['plan_start'],periods=72,freq='h');as_of=pd.Timestamp(as_of)
    evaluation_id='evaluation_'+uuid.uuid4().hex[:10]
    if as_of<index[-1]+pd.Timedelta(hours=1):
        result={'status':'Henüz değerlendirilemedi','as_of':str(as_of),'actual_cost_tl':None,'reference_actual_cost_tl':None,'actual_advantage_tl':None}
        save_json(folder/(evaluation_id+'.json'),result);return result
    with db_transaction(engine) as conn:
        actual=pd.read_sql(text('SELECT tarih_saat,"PTF (TL/MWh)" FROM wattrota.elektrik_fiyatlari WHERE tarih_saat >= :start AND tarih_saat < :end ORDER BY tarih_saat'),conn,params={'start':index[0].to_pydatetime(),'end':(index[-1]+pd.Timedelta(hours=1)).to_pydatetime()})
    series=actual.set_index('tarih_saat')['PTF (TL/MWh)'].reindex(index)
    if series.isna().any():
        result={'status':'Henüz değerlendirilemedi','as_of':str(as_of),'actual_cost_tl':None,'reference_actual_cost_tl':None,'actual_advantage_tl':None}
        save_json(folder/(evaluation_id+'.json'),result);return result
    firm=load_inputs(folder)
    plan=pd.read_csv(folder/'plan.csv',keep_default_na=False);plan.tarih_saat=pd.to_datetime(plan.tarih_saat)
    loads=pd.read_csv(folder/'loads.csv');loads.tarih_saat=pd.to_datetime(loads.tarih_saat)
    actual_cost,hourly=evaluated_cost(firm,plan,loads,series)
    ref_cost,ref_hourly=evaluated_cost(firm,firm['referans_plan'],firm['referans_yuklemeler'],series)
    prices=pd.read_csv(folder/'prices.csv');prices['gercek_fiyat_tl_mwh']=series.to_numpy()
    prices.to_csv(folder/(evaluation_id+'_prices.csv'),index=False)
    hourly.to_csv(folder/(evaluation_id+'_hourly.csv'),index=False)
    ref_hourly.to_csv(folder/(evaluation_id+'_reference_hourly.csv'),index=False)
    result={'status':'Değerlendirildi','as_of':str(as_of),'actual_cost_tl':actual_cost,'reference_actual_cost_tl':ref_cost,'actual_advantage_tl':ref_cost-actual_cost,'actual_savings_pct':100*(ref_cost-actual_cost)/ref_cost,'expected_cost_tl':manifest['expected_cost_tl'],'forecast_cost_difference_tl':actual_cost-manifest['expected_cost_tl'],'price_file':evaluation_id+'_prices.csv','hourly_file':evaluation_id+'_hourly.csv'}
    save_json(folder/(evaluation_id+'.json'),result);return result
def load_inputs(folder):
    times={'tarih_saat','gelis_zamani','en_erken_yukleme','teslim_zamani','serbest_birakma','tamamlanma_siniri','baslangic','bitis'}
    result={}
    for f in (Path(folder)/'inputs').glob('*.csv'):
        df=pd.read_csv(f,keep_default_na=False)
        for c in times.intersection(df.columns):df[c]=pd.to_datetime(df[c])
        result[f.stem]=df
    return result
def create_plan(seconds=15):
    total_started=time.perf_counter()
    run_id=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    folder=ROOT/'runs'/run_id;folder.mkdir(parents=True,exist_ok=False)
    save_json(folder/'request.json',{'created_at':now(),'historical_decision':str(DECISION),'solver_time_limit_seconds':seconds,'local_search_enabled':True,'local_subproblem_limit_seconds':10,'process_safety_limit_seconds':150,'new_optimization':True})
    engine=None
    try:
        engine=create_db_engine(SOURCE_PROJECT)
        firm,history=read_decision_inputs(engine,DECISION)
        index=pd.DatetimeIndex(firm['tesis_takvimi'].tarih_saat)
        prices,audit=build_planning_prices(history,index,DECISION)
        firm['fiyatlar']=pd.DataFrame({'tarih_saat':index,'PTF (TL/MWh)':prices.planlama_fiyati_tl_mwh.to_numpy()})
        (folder/'inputs').mkdir()
        for key,frame in firm.items():frame.to_csv(folder/'inputs'/(key+'.csv'),index=False)
        prices.to_csv(folder/'prices.csv',index=False)
        # Existing bounded local search; all objective and physical model code is unchanged.
        result=firma_cizelgele(firm,zaman_siniri=seconds,goreli_acik=.01,log_dosyasi=Path('runs')/run_id/'solver.log',yerel_iyilestirme=True)
        plan,loads,stocks,activity,hourly,summary,solver=result
        # A second physical calculation is deliberately independent of the solve.
        firma_planini_dogrula(firm,plan,loads)
        expected=float(summary['Karşılaştırılan toplam maliyet (TL)'])
        if abs(expected-solver['maliyet_tl'])>.02:raise ValueError('Amaç ve bağımsız maliyet eşleşmedi.')
        for name,frame in [('plan',plan),('loads',loads),('stocks',stocks),('activity',activity),('expected_hourly',hourly)]:frame.to_csv(folder/(name+'.csv'),index=False)
        sources={str(p.relative_to(LEGACY)):hashlib.sha256(p.read_bytes()).hexdigest() for p in LEGACY.rglob('*') if p.is_file() and p.suffix in ['.py','.json']}
        compare=plan.merge(firm['referans_plan'],on=['kaynak_id','tarih_saat'],suffixes=('','_ref'),validate='one_to_one')
        changed=int((compare.durum.ne(compare.durum_ref)|compare.urun_id.ne(compare.urun_id_ref)).sum())
        record={'run_id':run_id,'created_at':now(),'historical_decision':str(DECISION),'plan_start':str(index[0]),'plan_end_exclusive':str(index[-1]+pd.Timedelta(hours=1)),'hours':72,'announced_hours':int(prices.aciklanmis.sum()),'forecast_hours':int((~prices.aciklanmis).sum()),'database':'wattrota','factory_tables_read':17,'independent_validation':True,'expected_cost_tl':expected,'changed_resource_hours':changed,'delivered_tonnes':float(loads.miktar_ton.sum()),'solver':solver,'forecast_audit':audit,'publication_rule':'Normal süreç varsayımı: önceki gün 14.00; tarihsel yayın anı arşivi mevcut değil. Arıza/gecikme doğrulanmadı.','publication_source':PUBLICATION_SOURCE,'source_hashes':sources,'service_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        local_count=2+int(firm['kaynaklar'].kaynak_turu.eq('ogutme').sum())
        record['search']={'local_search_enabled':True,'local_subproblem_count':local_count,'local_subproblem_limit_seconds':10,'local_nominal_budget_seconds':10*local_count,'main_limit_seconds':seconds,'process_safety_limit_seconds':150,'old_solution_loaded':False}
        record['planning_wall_seconds']=time.perf_counter()-total_started
        save_json(folder/'decision.json',record)
        evaluation=evaluate_saved(folder,engine,pd.Timestamp.now(tz='Europe/Istanbul').tz_localize(None))
        save_json(folder/'result.json',{'run_id':run_id,'success':True,'decision':record,'evaluation':evaluation,'total_process_seconds':time.perf_counter()-total_started})
        return folder
    except Exception as exc:
        # Never dump DB exceptions/URLs. Preserve a failure with a safe category.
        safe=str(exc) if isinstance(exc,(ValueError,AssertionError)) else 'İşlem başarısız: '+type(exc).__name__+'. Bağlantı veya çalışma ortamını kontrol edin.'
        save_json(folder/'failure.json',{'run_id':run_id,'success':False,'stage':'planning_or_evaluation','error_type':type(exc).__name__,'message':safe,'created_at':now()})
        raise RuntimeError(safe) from None
    finally:
        if engine is not None:engine.dispose()

if __name__=='__main__':
    folder=create_plan();print(json.dumps({'run_folder':str(folder),'success':True},ensure_ascii=False))
