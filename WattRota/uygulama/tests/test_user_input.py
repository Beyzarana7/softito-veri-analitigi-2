from pathlib import Path
from io import BytesIO
import sys,unittest,zipfile,copy
import xml.etree.ElementTree as ET
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from user_input import validate_upload,read_xlsx,SCHEMA,MAX_BYTES,NS

TEMPLATE=ROOT/'outputs/veri_girisi/WattRota_Uretim_Verisi_Sablonu.xlsx'

def altered(table,cell=None,value=None,remove_column=False,remove_sheet=False,formula=False):
    """Mevcut örneğin ZIP içindeki tek hücresini değiştirir; test bellekte kalır."""
    data=TEMPLATE.read_bytes();source=zipfile.ZipFile(BytesIO(data));out=BytesIO()
    index=next(i for i,s in enumerate(SCHEMA) if s['key']==table)+3
    target=f'xl/worksheets/sheet{index}.xml'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dest:
        for name in source.namelist():
            raw=source.read(name)
            if name==target:
                root=ET.fromstring(raw)
                if remove_sheet:
                    for row in root.findall('s:sheetData/s:row',NS):root.find('s:sheetData',NS).remove(row)
                else:
                    c=root.find(f'.//s:c[@r="{cell}"]',NS)
                    if remove_column:
                        for row in root.findall('s:sheetData/s:row',NS):
                            for cc in list(row):
                                if cc.get('r','').rstrip('0123456789')==cell.rstrip('0123456789'):row.remove(cc)
                    else:
                        for child in list(c):c.remove(child)
                        c.attrib.pop('t',None)
                        if formula:ET.SubElement(c,'{'+NS['s']+'}f').text='1+1'
                        if value is not None:
                            if isinstance(value,str):c.set('t','inlineStr');ET.SubElement(ET.SubElement(c,'{'+NS['s']+'}is'),'{'+NS['s']+'}t').text=value
                            else:ET.SubElement(c,'{'+NS['s']+'}v').text=str(value)
                raw=ET.tostring(root)
            dest.writestr(name,raw)
    return out.getvalue()

class InputTests(unittest.TestCase):
    def check_bad(self,data,text):
        r=validate_upload(data,'test.xlsx');self.assertFalse(r.valid);self.assertTrue(any(text in e['Düzeltme'] for e in r.errors),r.errors)
    def test_valid_template(self):
        r=validate_upload(TEMPLATE.read_bytes(),TEMPLATE.name)
        self.assertTrue(r.valid,r.errors);self.assertEqual(len(r.tables),17);self.assertTrue(r.has_reference)
        self.assertEqual(len(r.tables['tesis_takvimi']),72)
        self.assertEqual(r.tables['siparisler'].miktar_ton.sum(),6720)
    def test_missing_column(self):self.check_bad(altered('kaynak_urun','C1',remove_column=True),'Eksik sütun')
    def test_wrong_type(self):self.check_bad(altered('kaynak_urun','C2','metin'),'Sayı girin')
    def test_negative_capacity(self):self.check_bad(altered('kaynak_urun','C2',-1),'Pozitif')
    def test_zero_capacity(self):self.check_bad(altered('kaynak_urun','C2',0),'Pozitif')
    def test_missing_value(self):self.check_bad(altered('kaynak_urun','C2',None),'Zorunlu')
    def test_wrong_relationship(self):self.check_bad(altered('kaynak_urun','B2','UR_YOK'),'bulunmayan')
    def test_duplicate_key(self):self.check_bad(altered('urunler','A3','UR01'),'tekrarlanıyor')
    def test_invalid_date(self):self.check_bad(altered('siparisler','F2','32.14.2025'),'Tarih biçimi')
    def test_subhour_date(self):self.check_bad(altered('siparisler','G2','2025-10-06 08:30'),'tam saat')
    def test_formula_rejected(self):self.check_bad(altered('kaynak_urun','C2',1,formula=True),'Formüller')
    def test_empty_sheet(self):self.check_bad(altered('urunler',remove_sheet=True),'başlıkları')
    def test_bad_extension(self):
        self.assertFalse(validate_upload(TEMPLATE.read_bytes(),'test.xlsm').valid)
    def test_size_limit(self):self.check_bad(b'x'*(MAX_BYTES+1),'5 MB')
    def test_bad_archive(self):self.check_bad(b'not excel','okunamadı')
    def test_missing_required_sheet(self):
        book=read_xlsx(TEMPLATE.read_bytes(),TEMPLATE.name);book.pop('Ürünler')
        with patch('user_input.read_xlsx',return_value=book):self.check_bad(b'x','Gerekli sayfa')
    def test_external_link_rejected(self):
        src=zipfile.ZipFile(BytesIO(TEMPLATE.read_bytes()));out=BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for name in src.namelist():z.writestr(name,src.read(name))
            z.writestr('xl/externalLinks/externalLink1.xml','<x/>')
        self.check_bad(out.getvalue(),'harici bağlantı')
    def test_path_traversal_rejected(self):
        out=BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('../outside.xml','<x/>')
        self.check_bad(out.getvalue(),'arşiv yapısı')
    def test_unsupported_active_initial_state(self):self.check_bad(altered('isletme_kurallari','D2','Evet'),'başlangıçta kapalı')
    def test_unsupported_indivisible_job(self):self.check_bad(altered('is_emirleri','G2','Hayır'),'bölünebilir')
    def test_bad_stock_bounds(self):self.check_bad(altered('stok_alanlari','F2',99999),'arasında')
    def test_unknown_route_step(self):self.check_bad(altered('rota_kaynaklari','B2',99),'Rota ve adım')
    def test_changed_order_without_initial_plan_is_not_feasibility(self):
        r=validate_upload(TEMPLATE.read_bytes(),TEMPLATE.name)
        self.assertTrue(r.valid)
        self.assertFalse(hasattr(r,'feasible'))
    def test_no_reference_sheets_required_for_preparation(self):
        # Sayfalar isteğe bağlı; motorla planlama için gerekli olmayı sürdürür.
        book=read_xlsx(TEMPLATE.read_bytes(),TEMPLATE.name)
        for k in ('referans_plan','referans_yuklemeler'):book.pop(next(s['sheet'] for s in SCHEMA if s['key']==k))
        with patch('user_input.read_xlsx',return_value=book):r=validate_upload(b'x','x.xlsx')
        self.assertTrue(r.valid,r.errors);self.assertFalse(r.has_reference)
    def test_no_database_or_solver_imports(self):
        import ast
        for name in ('user_input.py','input_page.py'):
            imports=[n.module for n in ast.walk(ast.parse((ROOT/name).read_text(encoding='utf-8'))) if isinstance(n,ast.ImportFrom)]
            self.assertFalse(set(imports)&{'service','kod.db','firma_cizelgeleme'})

if __name__=='__main__':unittest.main(verbosity=2)
