from contextlib import contextmanager
import psycopg
from .config import settings

@contextmanager
def connection():
    with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
        yield conn

def database_ok() -> bool:
    try:
        with connection() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1
    except psycopg.Error:
        return False
