from services.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    tables = conn.execute(text("""
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public';
    """)).fetchall()

print(tables)