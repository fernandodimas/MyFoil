import sqlalchemy
from sqlalchemy import text
import sys
import time

# Connection string provided by user
DB_URL = "postgresql://myfoil:myfoilpassword@192.168.16.250:5432/myfoil"

def wipe_db():
    print(f"Connecting to {DB_URL}...")
    try:
        engine = sqlalchemy.create_engine(DB_URL, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            print("Connected. Dropping schema 'public' (CASCADE)...")
            # Drop schema cascade removes all tables, views, etc.
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
            print("Schema dropped. Recreating 'public'...")
            conn.execute(text("CREATE SCHEMA public;"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
            # Optionally grant to specific user if needed, but 'public' usually suffices for default
            print("Database wiped successfully.")
    except Exception as e:
        print(f"Error wiping database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("WARNING: THIS WILL DELETE ALL DATA IN THE PRODUCTION DATABASE.")
    print("Waiting 5 seconds before proceeding...")
    time.sleep(5)
    wipe_db()
