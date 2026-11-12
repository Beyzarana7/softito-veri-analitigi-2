"""Kullanıcı çalışma kitaplarını bellekte okur. Veritabanına veya çözücüye erişmez."""
from pathlib import Path, PurePosixPath
from io import BytesIO
from dataclasses import dataclass, field
import json, math, re, zipfile
import xml.etree.ElementTree as ET
import pandas as pd

ROOT=Path(__file__).resolve().parent
SCHEMA=json.loads((ROOT/'input_schema.json').read_text(encoding='utf-8'))
MAX_BYTES=5*1024*1024
MAX_EXPANDED=32*1024*1024
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'

class InputError(ValueError):
    pass

@dataclass
class Validation:
    tables:dict=field(default_factory=dict)
    errors:list=field(default_factory=list)
    @property
    def valid(self):return not self.errors
    @property
    def has_reference(self):
        return all(k in self.tables and not self.tables[k].empty for k in ('referans_plan','referans_yuklemeler'))
    def add(self,sheet,row,column,message):
        if len(self.errors)<300:
            self.errors.append({'Sayfa':sheet,'Excel satırı':row,'Alan':column,'Düzeltme':message})

def _xml(z,name):
    raw=z.read(name)
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise InputError('Dosyada desteklenmeyen XML tanımı var. Yeni bir şablon kullanın.')
    return ET.fromstring(raw)

def read_xlsx(content:bytes,filename:str):
    """Hücreleri çıkarmadan, formül/makro/harici bağlantı kabul etmeden okur."""
    if Path(filename).suffix.lower()!='.xlsx':raise InputError('Yalnız .xlsx dosyası yükleyin.')
    if not content or len(content)>MAX_BYTES:raise InputError('Dosya boş veya 5 MB sınırını aşıyor.')
    try:
        with zipfile.ZipFile(BytesIO(content)) as z:
            items=z.infolist()
            if len(items)>1200 or sum(x.file_size for x in items)>MAX_EXPANDED:
                raise InputError('Dosyanın açılmış içeriği güvenli boyut sınırını aşıyor.')
            for item in items:
                p=PurePosixPath(item.filename)
                lower=item.filename.lower()
                if p.is_absolute() or '..' in p.parts or '\\' in item.filename or item.flag_bits&1:
                    raise InputError('Dosyanın arşiv yapısı desteklenmiyor.')
                if any(x in lower for x in ('vbaproject','externallinks/','embeddings/','activex/')):
                    raise InputError('Makro, gömülü nesne ve harici bağlantı içeren dosyalar kabul edilmez.')
                if item.file_size>max(1,item.compress_size)*1000:
                    raise InputError('Dosyanın sıkıştırma oranı güvenli sınırı aşıyor.')
                if lower.endswith('.rels'):
                    root=_xml(z,item.filename)
                    if any(x.get('TargetMode','').lower()=='external' for x in root):
                        raise InputError('Harici bağlantılar kabul edilmez; bağlantıları kaldırın.')
            wb=_xml(z,'xl/workbook.xml')
            props=wb.find('s:workbookPr',NS)
            if props is not None and props.get('date1904') in ('1','true'):
                raise InputError('1904 tarih sistemi desteklenmiyor; standart tarih sistemiyle kaydedin.')
            rels={x.get('Id'):x.get('Target') for x in _xml(z,'xl/_rels/workbook.xml.rels')}
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                strings=[''.join(e.itertext()) for e in _xml(z,'xl/sharedStrings.xml').findall('s:si',NS)]
            out={}
            total=0
            for sheet in wb.findall('s:sheets/s:sheet',NS):
                name=sheet.get('name')
                target=rels[sheet.get('{'+REL+'}id')]
                target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
                root=_xml(z,target)
                rows=[]
                for row in root.findall('s:sheetData/s:row',NS):
                    number=int(row.get('r','0'))
                    if number>10001:raise InputError('Bir sayfada en fazla 10.000 veri satırı kullanılabilir.')
                    cells={}
                    for c in row.findall('s:c',NS):
                        if c.find('s:f',NS) is not None:raise InputError(f'{name}: Formüller kabul edilmez. Hücreleri değer olarak yapıştırın.')
                        addr=c.get('r','');m=re.fullmatch(r'([A-Z]{1,3})([0-9]+)',addr)
                        if not m:raise InputError('Geçersiz hücre adresi.')
                        col=0
                        for x in m[1]:col=col*26+ord(x)-64
                        if col>100:raise InputError('Bir sayfada en fazla 100 sütun kullanılabilir.')
                        v=c.find('s:v',NS);value=v.text if v is not None else None
                        typ=c.get('t')
                        if typ=='s':value=strings[int(value)]
                        elif typ=='inlineStr':value=''.join(c.find('s:is',NS).itertext())
                        elif typ=='b':value=value=='1'
                        elif typ=='e':raise InputError(f'{name} {addr}: Excel hata hücresini düzeltin.')
                        elif typ not in ('str','d') and value is not None:
                            value=float(value)
                        cells[col]=value
                    if any(v is not None and v!='' for v in cells.values()):rows.append((number,cells))
                total+=len(rows)
                if total>50000:raise InputError('Çalışma kitabında en fazla 50.000 dolu satır kullanılabilir.')
                if name in out:raise InputError('Tekrarlanan sayfa adı.')
                out[name]=rows
            return out
    except InputError:raise
    except (zipfile.BadZipFile, KeyError, ValueError, ET.ParseError, IndexError, TypeError, OverflowError, RuntimeError, AttributeError) as exc:
        raise InputError('Excel dosyası okunamadı. İndirilen şablonu .xlsx olarak kaydedip tekrar yükleyin.') from exc

def _value(value,f):
    if value is None or isinstance(value,str) and not value.strip():
        if f['required']:raise ValueError('Zorunlu alan boş bırakılamaz.')
        return None
    typ=f['type']
    if typ=='str':
        if not isinstance(value,str):raise ValueError('Metin veya kimlik kodu girin; kodları metin olarak saklayın.')
        if len(value)>200:raise ValueError('Metin en fazla 200 karakter olabilir.')
        return value.strip()
    if typ=='bool':
        if isinstance(value,bool):return value
        if isinstance(value,str):
            v=value.strip().casefold()
            if v in ('evet','true','doğru'):return True
            if v in ('hayır','hayir','false','yanlış'):return False
        raise ValueError('Evet veya Hayır girin.')
    if typ=='number':
        if isinstance(value,bool):raise ValueError('Sayısal değer girin.')
        if isinstance(value,str) and not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?',value.strip()):
            raise ValueError('Sayı girin; metin ve binlik ayırıcı kullanmayın.')
        try:n=float(value.replace(',','.') if isinstance(value,str) else value)
        except (TypeError,ValueError):raise ValueError('Sayısal değer girin.')
        if not math.isfinite(n):raise ValueError('Sonlu bir sayı girin.')
        return n
    if typ=='datetime':
        if isinstance(value,bool):raise ValueError('Tarih ve saat girin.')
        if isinstance(value,(float,int)):
            if not 36526<=value<=73051:raise ValueError('2000–2100 arasında bir tarih girin.')
            t=pd.Timestamp('1899-12-30')+pd.Timedelta(seconds=round(value*86400))
        else:
            t=None
            for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%Y-%m-%d','%d.%m.%Y %H:%M','%d.%m.%Y %H:%M:%S'):
                try:t=pd.to_datetime(value,format=fmt,errors='raise');break
                except (ValueError,TypeError):pass
            if t is None:raise ValueError('Tarih biçimi: 2025-10-06 08:00 veya 06.10.2025 08:00.')
        if t.tzinfo is not None or t.minute or t.second or t.microsecond:
            raise ValueError('Türkiye yerel saatini tam saat olarak girin (örnek 08:00).')
        if not 2000<=t.year<=2100:raise ValueError('2000–2100 arasında bir tarih girin.')
        return t
    raise ValueError('Desteklenmeyen alan türü.')

def validate_tables(tables):
    """Tip dönüşümü sonrası anahtar, ilişki ve desteklenen yapının statik kontrolleri."""
    r=Validation(tables)
    specs={s['key']:s for s in SCHEMA}
    def err(t,msg,col='—',row='—'):
        spec=specs[t]
        label=next((f['label'] for f in spec['fields'] if f['key']==col),col)
        if isinstance(row,int):row=tables[t].attrs.get('excel_rows',{}).get(row-2,row)
        r.add(spec['sheet'],row,label,msg)
    for t,df in tables.items():
        s=specs[t]
        if df.duplicated(s['keys']).any():err(t,'Kimlik veya birleşik anahtar tekrarlanıyor. Her kayıt tekil olmalı.')
        for c in df:
            if next(f for f in s['fields'] if f['key']==c)['type']=='number':
                positive=c in ('kapasite_ton_saat','kapasite_ton','toplam_kapasite_ton','miktar_ton','tahsis_ton','guc_siniri_kw','adim_no','minimum_uretim_saat','minimum_durus_saat','hazirlik_saat')
                bad=(df[c]<=0) if positive else (df[c]<0)
                if bad.any():err(t,'Pozitif değer girin.' if positive else 'Negatif değer kullanılamaz.',c,int(df.index[bad][0])+2)
                if c in ('adim_no','minimum_uretim_saat','minimum_durus_saat','hazirlik_saat','baslangic_durum_suresi_saat') and (df[c]%1!=0).any():err(t,'Süre ve adım değerlerini tam sayı girin.',c)
    # Her dış anahtar bir ana tablodaki mevcut kayda bağlanır.
    refs={'urun_id':('urunler','urun_id'),'onceki_urun':('urunler','urun_id'),
          'sonraki_urun':('urunler','urun_id'),'baslangic_urun_ayari':('urunler','urun_id'),
          'kaynak_id':('kaynaklar','kaynak_id'),'siparis_id':('siparisler','siparis_id'),
          'is_emri_id':('is_emirleri','is_emri_id')}
    for t,df in tables.items():
        for c,(target,key) in refs.items():
            if c in df and not (t==target and c==key) and target in tables:
                if not df[c].dropna().isin(tables[target][key]).all():err(t,'İlgili ana tabloda bulunmayan kimlik kodu var.',c)
    def enum(t,c,values):
        if not tables[t][c].isin(values).all():err(t,'İzin verilen değerler: '+', '.join(values),c)
    enum('kaynaklar','kaynak_turu',['ogutme','paketleme','dokme_yukleme','torbali_yukleme'])
    enum('stok_alanlari','stok_turu',['dokme','torbali'])
    enum('siparisler','teslim_turu',['dokme','torbali'])
    enum('is_emirleri','islem_turu',['ogutme','paketleme'])
    enum('rotalar','teslim_turu',['dokme','torbali'])
    enum('rotalar','islem_turu',['ogutme','paketleme','dokme_yukleme','torbali_yukleme'])
    if tables['isletme_kurallari'].baslangicta_aktif.any():err('isletme_kurallari','Mevcut motor yalnız başlangıçta kapalı üretim kaynaklarını destekliyor.','baslangicta_aktif')
    if not tables['is_emirleri'].bolunebilir.all():err('is_emirleri','Mevcut motor yalnız bölünebilir iş emirlerini destekliyor.','bolunebilir')
    st=tables['stok_alanlari']
    if not {(p,s) for p in tables['urunler'].urun_id for s in ('dokme','torbali')}<=set(zip(st.urun_id,st.stok_turu)):
        err('stok_alanlari','Her ürün için dökme ve torbalı stok alanı tanımlayın.')
    if st.duplicated(['urun_id','stok_turu']).any():err('stok_alanlari','Ürün ve stok türü için yalnız bir stok alanı tanımlayın.')
    for c in ('baslangic_ton','son_hedef_ton'):
        if ((st[c]<st.minimum_ton)|(st[c]>st.kapasite_ton)).any():err('stok_alanlari','Değer alt stok sınırı ile kapasite arasında olmalı.',c)
    if len(tables['depo_kurallari'])!=1:err('depo_kurallari','Mevcut motor tek ortak torbalı depo bekliyor.')
    elif st.loc[st.stok_turu=='torbali','baslangic_ton'].sum()>tables['depo_kurallari'].toplam_kapasite_ton.iloc[0]:err('depo_kurallari','Başlangıç torbalı stok toplamı ortak depo kapasitesini aşıyor.')
    cal=tables['tesis_takvimi'].sort_values('tarih_saat')
    if len(cal)!=72 or not cal.tarih_saat.reset_index(drop=True).equals(pd.Series(pd.date_range(cal.tarih_saat.min(),periods=72,freq='h'),name='tarih_saat')):
        err('tesis_takvimi','Birbirini izleyen 72 tam saat girin; eksik veya tekrarlanan saat olmasın.')
    if (cal.temel_yuk_kw>cal.guc_siniri_kw).any():err('tesis_takvimi','Tesis temel yükü ortak güç sınırını aşamaz.')
    if cal.empty:return r
    start,end=cal.tarih_saat.min(),cal.tarih_saat.max()+pd.Timedelta(hours=1)
    hours=set(cal.tarih_saat)
    resources=tables['kaynaklar'];ru=tables['kaynak_urun'];routes=tables['rotalar']
    types=resources.set_index('kaynak_id').kaynak_turu.to_dict()
    capabilities=set(zip(ru.kaynak_id,ru.urun_id))
    production={k for k,v in types.items() if v in ('ogutme','paketleme')}
    if set(tables['isletme_kurallari'].kaynak_id)!=production:err('isletme_kurallari','Her üretim/paketleme makinesi için bir kural satırı tanımlayın; yükleme kaynaklarına eklemeyin.')
    for k in types:
        actual=tables['kaynak_takvimi'].loc[lambda x:x.kaynak_id==k,'tarih_saat']
        if len(actual)!=72 or set(actual)!=hours:err('kaynak_takvimi','Her makine için tesisle aynı 72 saati tanımlayın.')
        if k not in set(ru.kaynak_id):err('kaynak_urun','Her makine için en az bir uygun ürün ve kapasite tanımlayın.')
    for _,x in tables['bakimlar'].iterrows():
        if not start<=x.baslangic<x.bitis<=end:err('bakimlar','Bakım aralığı plan dönemi içinde ve başlangıçtan sonra bitmeli.')
        else:
            sub=tables['kaynak_takvimi'];sub=sub[(sub.kaynak_id==x.kaynak_id)&(sub.tarih_saat>=x.baslangic)&(sub.tarih_saat<x.bitis)]
            if sub.kullanilabilir.any():err('bakimlar','Bakım saatlerinde Makine Takvimi kullanılabilirliği Hayır olmalı.')
    for _,x in tables['siparisler'].iterrows():
        if not x.gelis_zamani<=x.en_erken_yukleme<x.teslim_zamani or not start<=x.en_erken_yukleme<x.teslim_zamani<=end:err('siparisler','Geliş ≤ en erken yükleme < teslim olmalı; yükleme aralığı plan dönemi içinde kalmalı.')
        rr=routes[routes.rota_id==x.rota_id]
        if rr.empty or not ((rr.urun_id==x.urun_id)&(rr.teslim_turu==x.teslim_turu)).all():err('siparisler','Rota, siparişin ürünü ve teslim türüyle eşleşmeli.','rota_id')
    for _,x in tables['is_emirleri'].iterrows():
        if not start<=x.serbest_birakma<x.tamamlanma_siniri<=end:err('is_emirleri','Üretim zaman aralığı plan dönemi içinde ve sıralı olmalı.')
    for rid,g in routes.groupby('rota_id'):
        g=g.sort_values('adim_no')
        expected=['ogutme','dokme_yukleme'] if g.teslim_turu.iloc[0]=='dokme' else ['ogutme','paketleme','torbali_yukleme']
        flows=[('hammadde','dokme'),('dokme','teslim')] if len(expected)==2 else [('hammadde','dokme'),('dokme','torbali'),('torbali','teslim')]
        if g.islem_turu.tolist()!=expected or g.adim_no.tolist()!=list(range(1,len(expected)+1)) or len(set(g.urun_id))!=1 or len(set(g.teslim_turu))!=1 or list(zip(g.girdi_stok_turu,g.cikti_stok_turu))!=flows:err('rotalar','Desteklenen sıra: öğütme → dökme yükleme veya öğütme → paketleme → torbalı yükleme; stok akışlarını ve adım sırasını kontrol edin.')
    for _,x in tables['rota_kaynaklari'].iterrows():
        rr=routes[(routes.rota_id==x.rota_id)&(routes.adim_no==x.adim_no)]
        if len(rr)!=1:err('rota_kaynaklari','Rota ve adım birleşimi Üretim Rotaları sayfasında bulunmalı.')
        elif types.get(x.kaynak_id)!=rr.iloc[0].islem_turu or (x.kaynak_id,rr.iloc[0].urun_id) not in capabilities:err('rota_kaynaklari','Makine türü ve uygun ürün kapasitesi rota adımıyla eşleşmiyor.')
    mapped=set(zip(tables['rota_kaynaklari'].rota_id,tables['rota_kaynaklari'].adim_no))
    if not set(zip(routes.rota_id,routes.adim_no))<=mapped:err('rota_kaynaklari','Her rota adımı için en az bir uygun makine tanımlayın.')
    for _,x in tables['isletme_kurallari'].iterrows():
        if (x.kaynak_id,x.baslangic_urun_ayari) not in capabilities:err('isletme_kurallari','Başlangıç ürün ayarı makinenin uygun ürünlerinden biri olmalı.')
    transitions=tables['urun_gecisleri']
    for _,x in transitions.iterrows():
        if x.onceki_urun==x.sonraki_urun or x.kaynak_id not in production or any((x.kaynak_id,p) not in capabilities for p in (x.onceki_urun,x.sonraki_urun)):err('urun_gecisleri','Geçiş yalnız üretim kaynağının iki farklı uygun ürünü arasında tanımlanabilir.')
    required={(k,a,b) for k in production for a in ru.loc[ru.kaynak_id==k,'urun_id'] for b in ru.loc[ru.kaynak_id==k,'urun_id'] if a!=b}
    if not required<=set(zip(transitions.kaynak_id,transitions.onceki_urun,transitions.sonraki_urun)):err('urun_gecisleri','Her üretim kaynağının farklı uygun ürünleri arasındaki iki yönlü geçişleri tanımlayın.')
    # İş emri-sipariş tahsisleri farklı işlem aşamalarında ayrı ayrı dengelenir.
    jobs=tables['is_emirleri'].set_index('is_emri_id');orders=tables['siparisler'].set_index('siparis_id');links=tables['is_emri_siparis_baglantisi']
    if jobs.index.is_unique and orders.index.is_unique:
        for _,x in links.iterrows():
            if x.is_emri_id in jobs.index and x.siparis_id in orders.index:
                j,o=jobs.loc[x.is_emri_id],orders.loc[x.siparis_id]
                if j.urun_id!=o.urun_id or (j.islem_turu=='paketleme' and o.teslim_turu!='torbali'):err('is_emri_siparis_baglantisi','Tahsis, aynı ürünün uygun sipariş aşamasına bağlanmalı.')
        for jid,j in jobs.iterrows():
            if abs(links.loc[links.is_emri_id==jid,'tahsis_ton'].sum()-j.miktar_ton)>1e-6:err('is_emri_siparis_baglantisi','İş emrine ayrılan toplam miktar iş emri miktarına eşit olmalı.')
        for oid,o in orders.iterrows():
            for stage in (['ogutme','paketleme'] if o.teslim_turu=='torbali' else ['ogutme']):
                jids=set(jobs.index[jobs.islem_turu==stage]);amount=links.loc[(links.siparis_id==oid)&links.is_emri_id.isin(jids),'tahsis_ton'].sum()
                if abs(amount-o.miktar_ton)>1e-6:err('is_emri_siparis_baglantisi','Her siparişin gerekli işlem aşamasındaki tahsis toplamı sipariş miktarına eşit olmalı.')
    if 'referans_plan' in tables and not tables['referans_plan'].empty:
        p=tables['referans_plan'];enum('referans_plan','durum',['kapali','uretim','hazirlik'])
        if set(zip(p.kaynak_id,p.tarih_saat))!={(k,t) for k in production for t in hours}:err('referans_plan','Başlangıç çizelgesi her üretim kaynağını 72 saat boyunca kapsamalı.')
        for _,x in p.iterrows():
            if x.durum in ('uretim','hazirlik') and (x.kaynak_id,x.urun_id) not in capabilities:err('referans_plan','Aktif saatte makineye uygun ürün kodu gerekli.')
            if x.durum=='uretim':
                if pd.isna(x.is_emri_id) or x.is_emri_id not in jobs.index:err('referans_plan','Üretim saatinde geçerli iş emri gerekli.')
                elif jobs.index.is_unique:
                    j=jobs.loc[x.is_emri_id]
                    if x.urun_id!=j.urun_id or types.get(x.kaynak_id)!=j.islem_turu:err('referans_plan','Üretim saati ürün ve işlem türü iş emriyle eşleşmeli.')
    if 'referans_yuklemeler' in tables:
        for _,x in tables['referans_yuklemeler'].iterrows():
            if x.tarih_saat not in hours:err('referans_yuklemeler','Yükleme saati tesis takviminde bulunmalı.')
            if x.siparis_id in orders.index and orders.index.is_unique:
                o=orders.loc[x.siparis_id]
                if not o.en_erken_yukleme<=x.tarih_saat<o.teslim_zamani or types.get(x.kaynak_id)!=o.teslim_turu+'_yukleme' or (x.kaynak_id,o.urun_id) not in capabilities:err('referans_yuklemeler','Yükleme zamanı, kaynak türü veya ürün siparişle uyumsuz.')
    return r

def validate_upload(content,filename):
    r=Validation()
    try:book=read_xlsx(content,filename)
    except InputError as exc:r.add('Dosya','—','—',str(exc));return r
    unknown=set(book)-{s['sheet'] for s in SCHEMA}-{'Kullanım','Alan Sözlüğü'}
    for name in sorted(unknown):r.add(name,'—','—','Tanınmayan sayfa. Şablon dışındaki sayfayı kaldırın veya doğru şablon adını kullanın.')
    for s in SCHEMA:
        name=s['sheet'];rows=book.get(name)
        if rows is None:
            if not s['optional']:r.add(name,'—','—','Gerekli sayfa bulunamadı. Şablondaki sayfa adını koruyun.')
            continue
        if not rows or rows[0][0]!=1:r.add(name,1,'—','Sütun başlıkları ilk satırda olmalı.');continue
        headers=list(rows[0][1].values())
        expected=[f['label'] for f in s['fields']]
        if len(set(headers))!=len(headers):r.add(name,1,'—','Tekrarlanan sütun başlığı var.');continue
        missing=[x for x in expected if x not in headers]
        extra=[x for x in headers if x not in expected]
        if missing or extra:r.add(name,1,'—','Eksik sütunlar: '+', '.join(missing)+'. Tanınmayan sütunlar: '+', '.join(str(x) for x in extra));continue
        positions={label:col for col,label in rows[0][1].items()}
        records=[]
        for rownum,cells in rows[1:]:
            record={}
            for f in s['fields']:
                try:record[f['key']]=_value(cells.get(positions[f['label']]),f)
                except ValueError as exc:r.add(name,rownum,f['label'],str(exc))
            records.append(record)
        if not records and not s['allow_empty']:r.add(name,2,'—','En az bir veri satırı girin.')
        r.tables[s['key']]=pd.DataFrame(records,columns=[f['key'] for f in s['fields']])
        r.tables[s['key']].attrs['excel_rows']={i:n for i,(n,_) in enumerate(rows[1:])}
    # Hatalı tipler üzerinde ilişki hesaplaması yapılmaz; ilk hatalar önce düzeltilir.
    if not r.errors:
        structural=validate_tables(r.tables);r.errors.extend(structural.errors)
    return r
