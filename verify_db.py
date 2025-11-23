import sys
import os
from pathlib import Path
import sqlite3

# Add src_python to path
sys.path.append(os.path.join(os.getcwd(), "src_python"))

try:
    from src_python import config
    print(f"Config loaded.")
    print(f"DB_NAME from config: {config.DB_NAME}")
    print(f"DATA_DIR from config: {config.DATA_DIR}")
    
    # Check directory
    if not config.DATA_DIR.exists():
        print(f"Creating DATA_DIR: {config.DATA_DIR}")
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    else:
        print(f"DATA_DIR exists.")

    # Test raw sqlite3 connection
    db_path = config.DB_NAME.replace("sqlite:///", "")
    print(f"Testing raw sqlite3 connection to: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        print("SUCCESS: Raw sqlite3 connection and table creation worked.")
    except Exception as e:
        print(f"FAILURE: Raw sqlite3 error: {e}")

    # Test SQLAlchemy
    print("Testing SQLAlchemy connection...")
    from src_python.database import engine, Base
    try:
        Base.metadata.create_all(bind=engine)
        print("SUCCESS: SQLAlchemy table creation worked.")
    except Exception as e:
        print(f"FAILURE: SQLAlchemy error: {e}")

except Exception as e:
    print(f"CRITICAL FAILURE: {e}")
