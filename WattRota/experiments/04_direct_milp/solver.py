"""Doğrulanmış MILP'nin ayrı kopyası; yalnız geçmiş sabitleme ve izleme ekleri içerir."""
import re
import time
import highspy
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from firma_cizelgeleme import maliyet_ve_ozet

def solve(v,zaman_siniri=120,goreli_acik=0.01,degisiklik_gideri=0.0,log_dosyasi=None,yerel_iyilestirme=False,baslangic_cozumu=None,fixed_prefix_hours=0):
    """Üretim, iş emri ataması, hazırlık ve yüklemeyi birlikte planla.

    HiGHS'e verilecek referans çözüm, hem bağımsız kontrol hem modelin
    bütün satırlarıyla doğrulanır. Süre sınırı ile karşılanamazlık ayrıdır.
    """
    if zaman_siniri<=0 or goreli_acik<0 or degisiklik_gideri<0:
        raise ValueError('Süre pozitif; açık ve değişiklik gideri negatif olmayan değer olmalı.')
    ref_h,ref_f,ref_s,ref_ozet=maliyet_ve_ozet(v,v['referans_plan'],v['referans_yuklemeler'],degisiklik_gideri)
    baslangic_plan,baslangic_yuklemeler=(v['referans_plan'],v['referans_yuklemeler']) if baslangic_cozumu is None else baslangic_cozumu
    bas_h,_,_,bas_ozet=maliyet_ve_ozet(v,baslangic_plan,baslangic_yuklemeler,degisiklik_gideri)
    if bas_ozet['Karşılaştırılan toplam maliyet (TL)']>ref_ozet['Karşılaştırılan toplam maliyet (TL)']+0.02:
        raise ValueError('Başlangıç çözümü referanstan daha pahalı olamaz.')
    zamanlar=pd.DatetimeIndex(v['tesis_takvimi']['tarih_saat'])
    n=len(zamanlar); t_index={t:i for i,t in enumerate(zamanlar)}
    kaynaklar=v['kaynaklar'].set_index('kaynak_id')
    mod=v['kaynak_urun'].set_index(['kaynak_id','urun_id'])
    kur=v['isletme_kurallari'].set_index('kaynak_id')
    gec=v['urun_gecisleri'].set_index(['kaynak_id','onceki_urun','sonraki_urun'])
    emir=v['is_emirleri'].set_index('is_emri_id')
    sip=v['siparisler'].set_index('siparis_id')
    stk=v['stok_alanlari'].set_index(['urun_id','stok_turu'])
    tak=v['kaynak_takvimi'].set_index(['kaynak_id','tarih_saat'])
    tesis=v['tesis_takvimi'].set_index('tarih_saat')
    fiyat=v['fiyatlar'].set_index('tarih_saat').loc[zamanlar,'PTF (TL/MWh)'].to_numpy(dtype=float)
    if not np.isfinite(fiyat).all() or np.any(fiyat<0):
        raise ValueError('Sonlu, negatif olmayan saatlik fiyatlar bekleniyor.')
    if kur['baslangicta_aktif'].any():
        raise ValueError('Bu firma sürümü kapalı başlangıç için tanımlıdır.')
    if not emir['bolunebilir'].all():
        raise ValueError('Bu firma modeli bölünebilir iş emirleri için tanımlıdır.')
    for s in ['minimum_uretim_saat','minimum_durus_saat']:
        if not ((kur[s]>=1)&(kur[s]%1==0)).all():
            raise ValueError('Minimum süreler pozitif tam saat olmalı.')
    if not ((gec['hazirlik_saat']>=1)&(gec['hazirlik_saat']%1==0)).all():
        raise ValueError('Hazırlık süreleri pozitif tam saat olmalı.')
    uygun={r:list(v['kaynak_urun'].loc[v['kaynak_urun']['kaynak_id']==r,'urun_id']) for r in kur.index}
    urunler=list(v['urunler']['urun_id'])
    kaynak_tur=kaynaklar['kaynak_turu'].to_dict()
    ref=v['referans_plan'].set_index(['kaynak_id','tarih_saat'])

    bedel=[]; alt=[]; ust=[]; tam=[]; adlar=[]
    def degisken(ad,lo=0,hi=1,integer=True,cost=0):
        i=len(bedel); adlar.append(ad); bedel.append(float(cost))
        alt.append(float(lo)); ust.append(float(hi)); tam.append(bool(integer))
        return i
    x={}; ayar={}; is_bas={}; on={}; start={}; stop={}; haz={}; atama={}
    stok={}; miktar={}; sevk_sec={}; yuk_aktif={}
    sabit_bedel=float(np.dot(tesis.loc[zamanlar,'temel_yuk_kw'].to_numpy()/1000,fiyat))
    for r in kur.index:
        k=kur.loc[r]
        for t,z in enumerate(zamanlar):
            on[r,t]=degisken(f'aktif[{r},{t}]',hi=int(tak.loc[(r,z),'kullanilabilir']))
            start[r,t]=degisken(f'baslatma[{r},{t}]',cost=k['baslatma_enerjisi_kwh']/1000*fiyat[t]+k['baslatma_elektrik_disi_gider_tl'])
            stop[r,t]=degisken(f'durdurma[{r},{t}]')
            for p in uygun[r]:
                x[r,p,t]=degisken(f'uretim[{r},{p},{t}]',cost=mod.loc[(r,p),'calisma_gucu_kw']/1000*fiyat[t])
                ayar[r,p,t]=degisken(f'ayar[{r},{p},{t}]')
                is_bas[r,p,t]=degisken(f'uretim_baslangici[{r},{p},{t}]')
    for (r,p,q),g in gec.iterrows():
        sure=int(g['hazirlik_saat'])
        for t in range(n-sure+1):
            enerji_bedeli=float(g['hazirlik_gucu_kw']/1000*fiyat[t:t+sure].sum())
            haz[r,p,q,t]=degisken(f'hazirlik[{r},{p},{q},{t}]',cost=enerji_bedeli+g['elektrik_disi_gider_tl'])
    for eid,e in emir.iterrows():
        for r in kur.index:
            p=e['urun_id']
            if kaynak_tur[r]==e['islem_turu'] and (r,p) in mod.index:
                for t,z in enumerate(zamanlar):
                    if e['serbest_birakma']<=z and z+pd.Timedelta(hours=1)<=e['tamamlanma_siniri']:
                        atama[eid,r,t]=degisken(f'is_emri[{eid},{r},{t}]')
    atama_gruplari={}
    for (eid,r,t),i in atama.items():
        atama_gruplari.setdefault((r,emir.loc[eid,'urun_id'],t),[]).append(i)
    yuk_kaynak=[r for r in kaynaklar.index if kaynak_tur[r] in ['dokme_yukleme','torbali_yukleme']]
    for r in yuk_kaynak:
        for t,z in enumerate(zamanlar):
            # Yükleme güçleri kaynak içinde sabit tanımlanmıştır.
            gucler=v['kaynak_urun'].loc[v['kaynak_urun']['kaynak_id']==r,'calisma_gucu_kw']
            if gucler.nunique()!=1:
                raise ValueError('Yükleme gücü kaynak içinde sabit olmalı.')
            yuk_aktif[r,t]=degisken(f'yukleme_aktif[{r},{t}]',hi=int(tak.loc[(r,z),'kullanilabilir']),cost=float(gucler.iloc[0])/1000*fiyat[t])
    for sid,s in sip.iterrows():
        tur='dokme_yukleme' if s['teslim_turu']=='dokme' else 'torbali_yukleme'
        for r in yuk_kaynak:
            if kaynak_tur[r]==tur and (r,s['urun_id']) in mod.index:
                for t,z in enumerate(zamanlar):
                    if tak.loc[(r,z),'kullanilabilir'] and z>=s['gelis_zamani'] and z>=s['en_erken_yukleme'] and z+pd.Timedelta(hours=1)<=s['teslim_zamani']:
                        miktar[sid,r,t]=degisken(f'sevk_ton[{sid},{r},{t}]',hi=min(s['miktar_ton'],mod.loc[(r,s['urun_id']),'kapasite_ton_saat']),integer=False)
                        sevk_sec[sid,r,t]=degisken(f'sevk_sec[{sid},{r},{t}]')
    for (p,tip),s in stk.iterrows():
        for t in range(n):
            stok[p,tip,t]=degisken(f'stok[{p},{tip},{t}]',lo=s['minimum_ton'],hi=s['kapasite_ton'],integer=False)

    # Hazırlığın kapsadığı saatler ve tamamlandığı an ayrı tutulur.
    kapsayan={(r,t):[] for r in kur.index for t in range(n)}
    biten={(r,t):[] for r in kur.index for t in range(n)}
    for key,i in haz.items():
        r,p,q,t=key; sure=int(gec.loc[(r,p,q),'hazirlik_saat'])
        for s in range(t,t+sure):
            kapsayan[r,s].append((p,q,t,i))
        if t+sure<n:
            biten[r,t+sure].append((p,q,i))

    # Plan değişikliği bir üretim kaynağının durum/ürün değişimi üzerinden ölçülür.
    if degisiklik_gideri:
        for r in kur.index:
            for t,z in enumerate(zamanlar):
                eski=ref.loc[(r,z)]
                if eski['durum']=='kapali':
                    bedel[on[r,t]]+=degisiklik_gideri
                else:
                    sabit_bedel+=degisiklik_gideri
                    if eski['durum']=='uretim':
                        bedel[x[r,eski['urun_id'],t]]-=degisiklik_gideri
                    else:
                        for p,q,bas,i in kapsayan[r,t]:
                            if q==eski['urun_id']:
                                bedel[i]-=degisiklik_gideri

    rows=[]; cols=[]; vals=[]; lb=[]; ub=[]; etiket=[]
    def kisit(ad,coef,lo=-np.inf,hi=np.inf):
        sat=len(lb); etiket.append(ad); lb.append(float(lo)); ub.append(float(hi))
        for i,c in coef.items():
            if c:
                rows.append(sat);cols.append(i);vals.append(float(c))
    for r in kur.index:
        k=kur.loc[r]; minprod=int(k['minimum_uretim_saat']); minoff=int(k['minimum_durus_saat'])
        for t,z in enumerate(zamanlar):
            a={on[r,t]:-1,**{x[r,p,t]:1 for p in uygun[r]}}
            for p,q,bas,i in kapsayan[r,t]:
                a[i]=1
            kisit('tek_faaliyet',a,0,0)
            kisit('tek_urun_ayari',{ayar[r,p,t]:1 for p in uygun[r]},1,1)
            for p in uygun[r]:
                kisit('uretim_ayari',{x[r,p,t]:1,ayar[r,p,t]:-1},hi=0)
                a={ayar[r,p,t]:1}
                if t==0:
                    deger=int(p==k['baslangic_urun_ayari'])
                    kisit('baslangic_ayari',a,deger,deger)
                else:
                    a[ayar[r,p,t-1]]=-1
                    for eski,yeni,i in biten[r,t]:
                        if eski==p:a[i]=a.get(i,0)+1
                        if yeni==p:a[i]=a.get(i,0)-1
                    kisit('ayar_akisi',a,0,0)
                # Saatlik üretim tam olarak uygun iş emirlerinden birine atanır.
                a={x[r,p,t]:-1}
                for i in atama_gruplari.get((r,p,t),[]):a[i]=1
                kisit('is_emri_atamasi',a,0,0)
                b=is_bas[r,p,t]
                a={b:1,x[r,p,t]:-1}
                if t:a[x[r,p,t-1]]=1
                kisit('blok_baslangici',a,lo=0)
                kisit('blok_aktif',{b:1,x[r,p,t]:-1},hi=0)
                if t:kisit('blok_onceki',{b:1,x[r,p,t-1]:1},hi=1)
                if t+minprod<=n:
                    a={x[r,p,s]:1 for s in range(t,t+minprod)};a[b]=-minprod
                    kisit('minimum_uretim',a,lo=0)
                else:kisit('ufuk_sonu_uretim',{b:1},0,0)
            b=start[r,t]; d=stop[r,t]
            if t==0:
                kisit('ilk_baslatma',{b:1,on[r,t]:-1},0,0);kisit('ilk_durdurma',{d:1},0,0)
            else:
                kisit('acilis_tanimi',{b:1,on[r,t]:-1,on[r,t-1]:1},lo=0)
                kisit('acilis_aktif',{b:1,on[r,t]:-1},hi=0)
                kisit('acilis_onceki',{b:1,on[r,t-1]:1},hi=1)
                kisit('kapanis_tanimi',{d:1,on[r,t-1]:-1,on[r,t]:1},lo=0)
                kisit('kapanis_onceki',{d:1,on[r,t-1]:-1},hi=0)
                kisit('kapanis_pasif',{d:1,on[r,t]:1},hi=1)
            for s in range(max(0,t-minoff),t):
                kisit('minimum_durus',{b:1,on[r,s]:1},hi=1)
            if t<minoff and t+k['baslangic_durum_suresi_saat']<minoff:
                kisit('baslangic_durus',{b:1},0,0)
            if t+minoff<=n:
                a={on[r,s]:1 for s in range(t,t+minoff)};a[d]=minoff
                kisit('kapanis_suresi',a,hi=minoff)
            else:kisit('ufuk_sonu_durus',{d:1},0,0)
    for (r,p,q,t),i in haz.items():
        kisit('hazirlik_baslangic_ayari',{i:1,ayar[r,p,t]:-1},hi=0)

    for eid,e in emir.iterrows():
        a={i:mod.loc[(r,e['urun_id']),'kapasite_ton_saat'] for (ee,r,t),i in atama.items() if ee==eid}
        kisit('is_emri_miktari',a,e['miktar_ton'],e['miktar_ton'])
    for sid,s in sip.iterrows():
        kisit('siparis_miktari',{i:1 for (ss,r,t),i in miktar.items() if ss==sid},s['miktar_ton'],s['miktar_ton'])
    for (sid,r,t),i in miktar.items():
        cap=mod.loc[(r,sip.loc[sid,'urun_id']),'kapasite_ton_saat']
        kisit('yukleme_kapasitesi',{i:1,sevk_sec[sid,r,t]:-cap},hi=0)
    for r in yuk_kaynak:
        for t in range(n):
            a={i:1 for (sid,rr,tt),i in sevk_sec.items() if rr==r and tt==t}
            a[yuk_aktif[r,t]]=-1;kisit('tek_yukleme',a,0,0)

    for t,z in enumerate(zamanlar):
        for (p,tip),s in stk.iterrows():
            cikan={i:1 for (sid,r,tt),i in miktar.items() if tt==t and sip.loc[sid,'urun_id']==p and sip.loc[sid,'teslim_turu']==tip}
            giren={}
            for r in kur.index:
                if (r,p) not in mod.index:continue
                q=mod.loc[(r,p),'kapasite_ton_saat']
                if kaynak_tur[r]=='ogutme' and tip=='dokme':giren[x[r,p,t]]=q
                if kaynak_tur[r]=='paketleme':
                    if tip=='dokme':cikan[x[r,p,t]]=q
                    else:giren[x[r,p,t]]=q
            a=dict(cikan)
            if t:
                a[stok[p,tip,t-1]]=-1;kisit('donem_basi_malzeme',a,hi=-s['minimum_ton'])
            else:kisit('ilk_saat_malzeme',a,hi=s['baslangic_ton']-s['minimum_ton'])
            a={stok[p,tip,t]:1,**cikan}
            for i,q in giren.items():a[i]=a.get(i,0)-q
            if t:a[stok[p,tip,t-1]]=-1;kisit('stok_dengesi',a,0,0)
            else:kisit('ilk_stok_dengesi',a,s['baslangic_ton'],s['baslangic_ton'])
            if t==n-1:kisit('son_stok_hedefi',{stok[p,tip,t]:1},s['son_hedef_ton'],s['son_hedef_ton'])
        kisit('ortak_torbali_depo',{stok[p,'torbali',t]:1 for p in urunler},hi=v['depo_kurallari'].iloc[0]['toplam_kapasite_ton'])
        a={x[r,p,t]:mod.loc[(r,p),'calisma_gucu_kw'] for r in kur.index for p in uygun[r]}
        for r in kur.index:
            a[start[r,t]]=kur.loc[r,'baslatma_enerjisi_kwh']
            for p,q,bas,i in kapsayan[r,t]:a[i]=gec.loc[(r,p,q),'hazirlik_gucu_kw']
        for r in yuk_kaynak:
            a[yuk_aktif[r,t]]=mod.loc[r].iloc[0]['calisma_gucu_kw']
        kisit('tesis_guc_siniri',a,hi=tesis.loc[z,'guc_siniri_kw']-tesis.loc[z,'temel_yuk_kw'])

    A=coo_matrix((vals,(rows,cols)),shape=(len(lb),len(bedel))).tocsc()
    c=np.asarray(bedel);lo=np.asarray(alt);hi=np.asarray(ust)
    lb=np.asarray(lb);ub=np.asarray(ub);integer=np.asarray(tam)
    # Kontrol edilmiş referansın modelde de uygun olduğunu sayısal olarak sınarız.
    warm=np.zeros(len(c))
    baslangic=baslangic_plan.set_index(['kaynak_id','tarih_saat'])
    ref_stok=bas_h.set_index(['urun_id','stok_turu','tarih_saat'])
    for r in kur.index:
        once_d='kapali';once_p='';cur=kur.loc[r,'baslangic_urun_ayari']
        for t,z in enumerate(zamanlar):
            s=baslangic.loc[(r,z)];d=s['durum'];p=s['urun_id']
            if once_d=='hazirlik' and (d!='hazirlik' or p!=once_p):cur=once_p
            warm[ayar[r,cur,t]]=1
            warm[on[r,t]]=int(d!='kapali')
            warm[start[r,t]]=int(once_d=='kapali' and d!='kapali')
            warm[stop[r,t]]=int(once_d!='kapali' and d=='kapali')
            if d=='uretim':
                warm[x[r,p,t]]=1;warm[atama[s['is_emri_id'],r,t]]=1
                warm[is_bas[r,p,t]]=int(once_d!='uretim' or once_p!=p)
            if d=='hazirlik' and (once_d!='hazirlik' or p!=once_p):warm[haz[r,cur,p,t]]=1
            once_d,once_p=d,p
    for y in baslangic_yuklemeler.itertuples(index=False):
        t=t_index[y.tarih_saat];key=(y.siparis_id,y.kaynak_id,t)
        warm[miktar[key]]=y.miktar_ton;warm[sevk_sec[key]]=1;warm[yuk_aktif[y.kaynak_id,t]]=1
    for (p,tip),s in stk.iterrows():
        for t,z in enumerate(zamanlar):warm[stok[p,tip,t]]=ref_stok.loc[(p,tip,z),'son_stok_ton']
    def denetle(values):
        activity=A@values
        bad=np.where((activity<lb-1e-5)|(activity>ub+1e-5))[0]
        if len(bad):
            raise ValueError(f'Model satırı sağlanmadı: {etiket[int(bad[0])]}, satır {int(bad[0])}')
        if np.any(values<lo-1e-5) or np.any(values>hi+1e-5) or np.max(np.abs(values[integer]-np.round(values[integer])))>1e-5:
            raise ValueError('Değişken sınırı/tamsayılılık sağlanmadı.')
    if fixed_prefix_hours not in (0,24,48):
        raise ValueError('Sabit geçmiş yalnız 0, 24 veya 48 saat olabilir.')
    fixed_count=0
    for i,name in enumerate(adlar):
        match=re.search(r',([0-9]+)\]$',name)
        if match is None:
            raise ValueError('Saat indeksi olmayan model değişkeni.')
        if int(match.group(1)) < fixed_prefix_hours:
            # Önceki fiziksel planın kanonik warm-start değerleri: boş yükleme seçimleri taşınmaz.
            lo[i]=warm[i];hi[i]=warm[i];fixed_count+=1
    denetle(warm)
    if not np.isclose(c@warm+sabit_bedel,bas_ozet['Karşılaştırılan toplam maliyet (TL)'],atol=0.01,rtol=0):
        raise ValueError('Referans model amacı ile bağımsız maliyet uyuşmuyor.')

    lp=highspy.HighsLp()
    lp.col_names_=adlar
    lp.num_col_=len(c);lp.num_row_=len(lb)
    lp.col_cost_=c;lp.col_lower_=lo;lp.col_upper_=hi
    lp.row_lower_=lb;lp.row_upper_=ub;lp.offset_=sabit_bedel
    lp.integrality_=[highspy.HighsVarType.kInteger if b else highspy.HighsVarType.kContinuous for b in tam]
    lp.a_matrix_.format_=highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_=A.indptr.astype(np.int32);lp.a_matrix_.index_=A.indices.astype(np.int32);lp.a_matrix_.value_=A.data
    solver=highspy.Highs()
    solver.setOptionValue('output_flag',bool(log_dosyasi))
    solver.setOptionValue('log_to_console',False)
    if log_dosyasi:solver.setOptionValue('log_file',str(log_dosyasi))
    solver.setOptionValue('time_limit',float(zaman_siniri));solver.setOptionValue('mip_rel_gap',float(goreli_acik))
    solver.setOptionValue('random_seed',42);solver.setOptionValue('threads',1)
    solver.passModel(lp)
    solver.setSolution(len(warm),np.arange(len(warm),dtype=np.int32),warm)
    yerel_bas=time.perf_counter()
    yerel_sonuclar=[]
    if yerel_iyilestirme and n>12:
        # Önce bazı kaynaklar sabit tutularak başlangıç çözümü iyileştirilir.
        # Bu alt problemler aynı kısıtları kullanır; global optimum kanıtı değildir.
        kaynak_indeks={r:[] for r in kur.index}
        for sozluk in [on,start,stop,x,ayar,is_bas,haz]:
            for key,i in sozluk.items():kaynak_indeks[key[0]].append(i)
        for (eid,r,t),i in atama.items():kaynak_indeks[r].append(i)
        ogutuculer=[r for r in kur.index if kaynak_tur[r]=='ogutme']
        paketleyiciler=[r for r in kur.index if kaynak_tur[r]=='paketleme']
        serbest_gruplar=[[]]+[paketleyiciler]+[[r]+paketleyiciler for r in ogutuculer]
        for serbest in serbest_gruplar:
            sabit=np.array([i for r,indeks in kaynak_indeks.items() if r not in serbest for i in indeks],dtype=np.int32)
            solver.changeColsBounds(len(sabit),sabit,warm[sabit],warm[sabit])
            solver.setOptionValue('time_limit',10.0)
            # Küçük alt problemlerde %1 açık, küçük gerçek kazançları kaçırabilir.
            solver.setOptionValue('mip_rel_gap',min(float(goreli_acik),0.000001))
            solver.setSolution(len(warm),np.arange(len(warm),dtype=np.int32),warm)
            solver.run();s=solver.getSolution();inf=solver.getInfo()
            if s.value_valid and inf.primal_solution_status==highspy.SolutionStatus.kSolutionStatusFeasible:
                aday=np.asarray(s.col_value);denetle(aday)
                if c@aday<c@warm-1e-5:warm=aday.copy()
            yerel_sonuclar.append({'serbest_kaynaklar':list(serbest),'maliyet_tl':float(c@warm+sabit_bedel),
                                  'durum':solver.modelStatusToString(solver.getModelStatus()),
                                  'goreli_acik':float(inf.mip_gap)})
            solver.changeColsBounds(len(sabit),sabit,lo[sabit],hi[sabit])
        solver.setOptionValue('time_limit',float(zaman_siniri))
        solver.setOptionValue('mip_rel_gap',float(goreli_acik))
        solver.setSolution(len(warm),np.arange(len(warm),dtype=np.int32),warm)
    yerel_sure=time.perf_counter()-yerel_bas
    bas=time.perf_counter();solver.run();sure=time.perf_counter()-bas
    info=solver.getInfo();status=solver.getModelStatus();sol=solver.getSolution()
    if not sol.value_valid or info.primal_solution_status!=highspy.SolutionStatus.kSolutionStatusFeasible:
        raise ValueError(f'Uygun plan bulunamadı: {solver.modelStatusToString(status)}')
    values=np.asarray(sol.col_value);denetle(values)
    plan=v['referans_plan'][['kaynak_id','tarih_saat']].copy()
    plan['durum']='kapali';plan['urun_id']='';plan['is_emri_id']=''
    pi=plan.set_index(['kaynak_id','tarih_saat']).index
    yer={key:i for i,key in enumerate(pi)}
    for (eid,r,t),i in atama.items():
        if values[i]>0.5:
            plan.loc[yer[r,zamanlar[t]],['durum','urun_id','is_emri_id']]=['uretim',emir.loc[eid,'urun_id'],eid]
    for (r,p,q,t),i in haz.items():
        if values[i]>0.5:
            for tt in range(t,t+int(gec.loc[(r,p,q),'hazirlik_saat'])):
                plan.loc[yer[r,zamanlar[tt]],['durum','urun_id','is_emri_id']]=['hazirlik',q,'']
    yuklemeler=pd.DataFrame([[sid,r,zamanlar[t],float(values[i])] for (sid,r,t),i in miktar.items() if values[i]>1e-6],
                           columns=['siparis_id','kaynak_id','tarih_saat','miktar_ton']).sort_values(['tarih_saat','kaynak_id']).reset_index(drop=True)
    hareket,faaliyet,saatlik,ozet=maliyet_ve_ozet(v,plan,yuklemeler,degisiklik_gideri)
    if not np.isclose(ozet['Karşılaştırılan toplam maliyet (TL)'],info.objective_function_value,atol=0.02,rtol=0):
        raise ValueError('Önerilen planın maliyeti çözücü amacıyla uyuşmuyor.')
    if ozet['Karşılaştırılan toplam maliyet (TL)']>ref_ozet['Karşılaştırılan toplam maliyet (TL)']+0.02:
        raise ValueError('Önerilen çözüm başlangıçtaki uygun referanstan daha pahalı.')
    if ozet['Karşılaştırılan toplam maliyet (TL)']>bas_ozet['Karşılaştırılan toplam maliyet (TL)']+0.02:
        raise ValueError('Önerilen çözüm doğrulanmış başlangıç çözümünden daha pahalı.')
    bilgi=dict(durum=solver.modelStatusToString(status),tolerans_icinde_optimum=status==highspy.HighsModelStatus.kOptimal,
               sure_saniye=sure,goreli_acik=float(info.mip_gap),alt_sinir_tl=float(info.mip_dual_bound),
               maliyet_tl=float(info.objective_function_value),degisken_sayisi=len(c),kisit_sayisi=len(lb),
               sure_siniri_saniye=zaman_siniri,hedef_goreli_acik=goreli_acik,
               degisiklik_gideri_tl_kaynak_saat=degisiklik_gideri,referans_model_kontrolu=baslangic_cozumu is None,
               baslangic_model_kontrolu=True,
               bagimsiz_plan_kontrolu=True,bagimsiz_maliyet_kontrolu=True,cozucu_surumu=solver.version(),
               baslangic_iyilestirmeleri=yerel_sonuclar,yerel_arama_saniye=yerel_sure,
               toplam_cozum_saniye=yerel_sure+sure,
               baslangic_maliyet_tl=float(bas_ozet['Karşılaştırılan toplam maliyet (TL)']))
    bilgi.update(fixed_prefix_hours=fixed_prefix_hours,fixed_columns=fixed_count,
                 mip_node_count=int(info.mip_node_count),time_limit_reached=status==highspy.HighsModelStatus.kTimeLimit)
    return plan,yuklemeler,hareket,faaliyet,saatlik,ozet,bilgi
