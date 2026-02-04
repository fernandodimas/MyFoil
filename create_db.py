import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def create_db():
    dsn = "postgresql://myfoil:myfoilpassword@193.123.107.250:5432/postgres"
    try:
        conn = psycopg2.connect(dsn)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        print("Conectado ao Postgres. Criando banco 'myfoillocal'...")
        cur.execute("CREATE DATABASE myfoillocal;")
        print("Banco 'myfoillocal' criado com sucesso!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao criar banco: {e}")

if __name__ == "__main__":
    create_db()
