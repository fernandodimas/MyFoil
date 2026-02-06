
import os
import psycopg2

url = "postgresql://myfoil:myfoilpassword@192.168.16.250:5432/myfoillocal"
try:
    print(f"Tentando conectar ao Postgres: {url}")
    conn = psycopg2.connect(url, connect_timeout=5)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user FROM \"user\";")
    users = cursor.fetchall()
    print(f"Usuários encontrados no Postgres: {users}")
    conn.close()
except Exception as e:
    print(f"Erro ao conectar ao Postgres: {e}")
