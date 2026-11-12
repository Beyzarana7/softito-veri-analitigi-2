"""Mevcut fabrika sözlüğünden şablon metaverisini ve örnekleri üretir; çözüm çalıştırmaz."""
from pathlib import Path
import csv, json

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'data/synthetic/firma_01'
INPUT = ROOT / 'runs/20261111_232421_67cf3c75/inputs'
NAMES = {
    'urunler':'Ürünler', 'kaynaklar':'Makineler', 'kaynak_urun':'Makine Kapasiteleri',
    'isletme_kurallari':'İşletme Kuralları', 'urun_gecisleri':'Ürün Geçişleri',
    'stok_alanlari':'Stok Alanları', 'depo_kurallari':'Depo Kuralları',
    'rotalar':'Üretim Rotaları', 'rota_kaynaklari':'Rota Makineleri',
    'siparisler':'Siparişler', 'is_emirleri':'İş Emirleri',
    'is_emri_siparis_baglantisi':'İş Emri Sipariş Bağı',
    'kaynak_takvimi':'Makine Takvimi', 'bakimlar':'Bakımlar',
    'tesis_takvimi':'Tesis Takvimi', 'referans_plan':'Başlangıç Çizelgesi',
    'referans_yuklemeler':'Başlangıç Yüklemeleri',
}
KEYS = {
    'urunler':['urun_id'], 'kaynaklar':['kaynak_id'], 'kaynak_urun':['kaynak_id','urun_id'],
    'isletme_kurallari':['kaynak_id'], 'urun_gecisleri':['kaynak_id','onceki_urun','sonraki_urun'],
    'stok_alanlari':['stok_id'], 'depo_kurallari':['depo_id'],
    'rotalar':['rota_id','adim_no'], 'rota_kaynaklari':['rota_id','adim_no','kaynak_id'],
    'siparisler':['siparis_id'], 'is_emirleri':['is_emri_id'],
    'is_emri_siparis_baglantisi':['is_emri_id','siparis_id'],
    'kaynak_takvimi':['kaynak_id','tarih_saat'], 'bakimlar':['kaynak_id','baslangic','bitis'],
    'tesis_takvimi':['tarih_saat'], 'referans_plan':['kaynak_id','tarih_saat'],
    'referans_yuklemeler':['kaynak_id','tarih_saat'],
}
LABELS = {
    'urun_id':'Ürün kodu','urun_adi':'Ürün adı','kaynak_id':'Makine kodu','kaynak_adi':'Makine adı',
    'kaynak_turu':'Makine türü','kapasite_ton_saat':'Kapasite (ton/saat)','calisma_gucu_kw':'Çalışma gücü (kW)',
    'minimum_uretim_saat':'En az üretim süresi (saat)','minimum_durus_saat':'En az duruş süresi (saat)',
    'baslangicta_aktif':'Başlangıçta çalışıyor mu','baslangic_durum_suresi_saat':'Başlangıç durumunda geçen süre (saat)',
    'baslangic_urun_ayari':'Başlangıç ürün ayarı','baslatma_enerjisi_kwh':'Başlatma enerjisi (kWh)',
    'baslatma_elektrik_disi_gider_tl':'Başlatma ek gideri (TL)','onceki_urun':'Önceki ürün kodu',
    'sonraki_urun':'Sonraki ürün kodu','hazirlik_saat':'Geçiş süresi (saat)',
    'hazirlik_gucu_kw':'Geçiş gücü (kW)','elektrik_disi_gider_tl':'Elektrik dışı gider (TL)',
    'stok_id':'Stok alanı kodu','stok_turu':'Stok türü','minimum_ton':'Alt stok sınırı (ton)',
    'kapasite_ton':'Stok kapasitesi (ton)','baslangic_ton':'Başlangıç stoku (ton)',
    'son_hedef_ton':'Dönem sonu hedefi (ton)','depo_id':'Depo kodu','toplam_kapasite_ton':'Ortak depo kapasitesi (ton)',
    'rota_id':'Rota kodu','teslim_turu':'Teslim türü','adim_no':'Adım sırası','islem_turu':'İşlem türü',
    'girdi_stok_turu':'Girdi stok türü','cikti_stok_turu':'Çıktı stok türü','siparis_id':'Sipariş kodu',
    'miktar_ton':'Miktar (ton)','gelis_zamani':'Sipariş geliş zamanı','en_erken_yukleme':'En erken yükleme',
    'teslim_zamani':'Son teslim zamanı','is_emri_id':'İş emri kodu','serbest_birakma':'En erken üretim',
    'tamamlanma_siniri':'Üretim tamamlanma sınırı','bolunebilir':'Bölünebilir mi','tahsis_ton':'Ayrılan miktar (ton)',
    'tarih_saat':'Saat başlangıcı','kullanilabilir':'Kullanılabilir mi','baslangic':'Başlangıç zamanı',
    'bitis':'Bitiş zamanı','temel_yuk_kw':'Tesis temel yükü (kW)','guc_siniri_kw':'Ortak güç sınırı (kW)',
    'durum':'Çalışma durumu',
}

def main():
    dictionary = list(csv.DictReader((SOURCE/'veri_sozlugu.csv').open(encoding='utf-8-sig')))
    tables=[]
    for name,title in NAMES.items():
        rows=list(csv.DictReader((INPUT/f'{name}.csv').open(encoding='utf-8-sig')))
        columns=list(rows[0])
        fields=[]
        for col in columns:
            meta=next((x for x in dictionary if x['dosya']==name+'.csv' and x['alan']==col),None)
            raw=meta['veri_turu'] if meta else ('datetime' if col=='tarih_saat' else 'float64' if col=='miktar_ton' else 'str')
            typ='datetime' if 'datetime' in raw else 'bool' if raw=='bool' else 'number' if raw.startswith(('int','float')) else 'str'
            nullable=name=='referans_plan' and col in ('urun_id','is_emri_id')
            fields.append(dict(key=col,label=LABELS[col],type=typ,unit=meta['birim'] if meta else {'miktar_ton':'ton','tarih_saat':'tarih-saat'}.get(col,'—'),
                description=meta['aciklama'] if meta else LABELS[col],required=not nullable,
                example=next((x[col] for x in rows if x[col]),'')))
        converted=[]
        for row in rows:
            d={}
            for f in fields:
                value=row[f['key']]
                if not value:value=None
                elif f['type']=='number':value=float(value)
                elif f['type']=='bool':value=value.lower()=='true'
                d[f['key']]=value
            converted.append(d)
        tables.append(dict(key=name,sheet=title,keys=KEYS[name],fields=fields,rows=converted,
            optional=name in ('referans_plan','referans_yuklemeler'),
            allow_empty=name in ('bakimlar','urun_gecisleri','referans_plan','referans_yuklemeler')))
    (ROOT/'input_schema.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(tables)} tablo, {sum(len(t["fields"]) for t in tables)} alan')

if __name__=='__main__':main()
