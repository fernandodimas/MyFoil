import sys
import os
from sqlalchemy import create_engine, text

# Adicionar o diretório atual ao path para importar configs
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'app'))

try:
    from app.constants import MYFOIL_DB
except ImportError:
    DB_FILE = os.path.join(os.getcwd(), 'app', 'config', 'myfoil.db')
    MYFOIL_DB = f"sqlite:///{DB_FILE}"

def fix_stuck_jobs():
    print(f"🔧 Cleaning jobs in: {MYFOIL_DB}")
    try:
        engine = create_engine(MYFOIL_DB)
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=30000"))
            
            update = conn.execute(text("""
                UPDATE system_jobs 
                SET status = 'failed', error = 'Server restart', completed_at = CURRENT_TIMESTAMP
                WHERE status IN ('running', 'scheduled')
            """))
            conn.commit()
            print(f"✅ Cleared {update.rowcount} jobs.")
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    return True

if __name__ == "__main__":
    fix_stuck_jobs()
