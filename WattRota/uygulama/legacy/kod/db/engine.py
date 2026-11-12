"""Bağlantı değerlerini yalnız .env'den alır; URL veya değerleri loglamaz."""
from contextlib import contextmanager
from pathlib import Path
import os

from dotenv import dotenv_values
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


class ConfigurationError(RuntimeError):
    pass


class DatabaseError(RuntimeError):
    pass


def create_db_engine(project):
    env = Path(project) / '.env'
    keys = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if not env.is_file() and not all(os.environ.get(k) for k in keys):
        raise ConfigurationError('Proje kökünde .env bulunamadı; değerleri sohbete göndermeden yerelde hazırlayın.')
    values = dotenv_values(env, interpolate=False) if env.is_file() else {}
    values.update({k:os.environ[k] for k in keys if os.environ.get(k) is not None})
    keys = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    missing = [k for k in keys if values.get(k) is None or values[k] == '']
    if missing:
        raise ConfigurationError('Eksik veya boş .env alanları: ' + ', '.join(missing))
    try:
        port = int(values['DB_PORT'])
    except (TypeError, ValueError):
        raise ConfigurationError('DB_PORT geçerli bir port numarası olmalı.') from None
    if not 1 <= port <= 65535:
        raise ConfigurationError('DB_PORT geçerli aralıkta olmalı.')
    if values['DB_NAME'] != 'wattrota':
        raise ConfigurationError('Bu modül yalnız wattrota veritabanı için yapılandırılmıştır.')
    url = URL.create('postgresql+psycopg', username=values['DB_USER'], password=values['DB_PASSWORD'],
                     host=values['DB_HOST'], port=port, database=values['DB_NAME'])
    return create_engine(url, echo=False, hide_parameters=True, pool_pre_ping=True,
                         pool_size=2, max_overflow=0,
                         connect_args={'connect_timeout':10, 'application_name':'WattRota'})


@contextmanager
def db_transaction(engine, write=False):
    conn = None
    try:
        conn = engine.connect().execution_options(isolation_level='REPEATABLE READ')
        with conn.begin():
            if not write:
                conn.execute(text('SET TRANSACTION READ ONLY'))
            yield conn
    except SQLAlchemyError:
        raise DatabaseError('Veritabanı işlemi başarısız; bağlantı değerleri ve hata parametreleri gösterilmedi.') from None
    finally:
        if conn is not None:
            conn.close()
