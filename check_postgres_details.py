
import os
import psycopg2

url = "postgresql://myfoil:myfoilpassword@192.168.16.250:5432/myfoillocal"
try:
    conn = psycopg2.connect(url, connect_timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    tables = cursor.fetchall()
    print(f"Tabelas no Postgres: {tables}")
    
    if ('user',) in tables:
        cursor.execute("SELECT count(*) FROM \"user\";")
        count = cursor.fetchone()[0]
        print(f"Número de usuários: {count}")
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
