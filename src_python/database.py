from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DB_NAME

# 1. Base Sınıfını Burada Tanımlıyoruz (Döngüyü Kırmak İçin)
class Base(DeclarativeBase):
    pass

# 2. Veritabanı URL Ayarı (SQLite vs PostgreSQL)
connect_args = {}

if "sqlite" in DB_NAME:
    # SQLite Ayarları
    if not DB_NAME.startswith("sqlite"):
        SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_NAME}"
    else:
        SQLALCHEMY_DATABASE_URL = DB_NAME
    connect_args = {"check_same_thread": False}
else:
    # PostgreSQL ve Diğerleri
    SQLALCHEMY_DATABASE_URL = DB_NAME
    # Postgres için check_same_thread gerekmez

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Modelleri burada, fonksiyon içinde import ediyoruz
    import models 
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
