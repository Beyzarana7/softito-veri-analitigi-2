"""Mevcut 20 firma tablosunun sütun ve anahtar sözlüğünü katalogdan çıkarır."""
from pathlib import Path
from sqlalchemy import inspect

from .engine import db_transaction
from .readers import BASE_TABLES


def export_dictionary(engine,destination):
    lines=['# WattRota veri sözlüğü taslağı','',
           'PostgreSQL kataloglarından otomatik çıkarılmıştır. Şema: `wattrota`; zaman alanları Türkiye yerel zamanıdır. Bağlantı bilgileri bu dosyada bulunmaz.','']
    with db_transaction(engine) as conn:
        inspector=inspect(conn)
        names=inspector.get_table_names(schema='wattrota')
        if set(names)!=set(BASE_TABLES) or len(names)!=20:
            raise ValueError('Beklenen 20 firma tablosu katalogla eşleşmiyor.')
        for name in sorted(names):
            pk=inspector.get_pk_constraint(name,schema='wattrota')['constrained_columns']
            fks=inspector.get_foreign_keys(name,schema='wattrota')
            lines += [f'## {name}','',f"Birincil anahtar: {', '.join(pk)}",'',
                      '| Sütun | PostgreSQL tipi | NULL olabilir | PK | FK hedefi |','|---|---|---|---|---|']
            for column in inspector.get_columns(name,schema='wattrota'):
                targets=[]
                for fk in fks:
                    if column['name'] in fk['constrained_columns']:
                        i=fk['constrained_columns'].index(column['name'])
                        targets.append(f"{fk.get('referred_schema') or 'wattrota'}.{fk['referred_table']}.{fk['referred_columns'][i]}")
                lines.append(f"| {column['name']} | {column['type']} | {'Evet' if column['nullable'] else 'Hayır'} | {'Evet' if column['name'] in pk else ''} | {'; '.join(targets)} |")
            lines += ['', 'Yabancı anahtarlar:']
            for fk in fks:
                lines.append(f"- ({', '.join(fk['constrained_columns'])}) → {fk.get('referred_schema') or 'wattrota'}.{fk['referred_table']} ({', '.join(fk['referred_columns'])})")
            if not fks: lines.append('- Yok.')
            lines.append('')
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return len(names)
