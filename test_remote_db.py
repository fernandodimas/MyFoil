
import psycopg2
import sys

def test_conn():
    ip = "193.123.107.250"
    user = "myfoil"
    password = "myfoilpassword"
    db_name = "postgres"
    
    dsn = f"postgresql://{user}:{password}@{ip}:5432/{db_name}"
    print(f"Testando conexão com {dsn}...")
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        print("✅ Conectado com sucesso!")
        conn.close()
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    test_conn()
