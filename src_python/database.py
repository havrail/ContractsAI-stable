from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import DB_NAME
from models import Base

# DB_NAME might already be a full URL if from .env
if DB_NAME.startswith("sqlite:///"):
    SQLALCHEMY_DATABASE_URL = DB_NAME
else:
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_NAME}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
