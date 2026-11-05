from collections.abc import Generator
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models import Base

connect_args = {}
db_url = settings.sqlalchemy_database_url

if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    # Timeout de 10 segundos para no bloquear el arranque
    connect_args["connect_timeout"] = 10

try:
    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
except Exception as e:
    print(f"[DB] Error creando engine para {db_url}: {e}", file=sys.stderr, flush=True)
    engine = create_engine("sqlite:///./asistencia.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    global engine, SessionLocal
    try:
        print(f"[DB] Conectando y creando tablas con URL: {engine.url.render_as_string(hide_password=True)}", flush=True)
        Base.metadata.create_all(bind=engine)
        print("[DB] Tablas inicializadas exitosamente.", flush=True)
    except Exception as e:
        print(f"[DB] ADVERTENCIA: No se pudo conectar a la base de datos remota ({e}).", file=sys.stderr, flush=True)
        print("[DB] Activando base de datos SQLite local de respaldo para mantener el servicio activo...", file=sys.stderr, flush=True)
        engine = create_engine("sqlite:///./asistencia.db", connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        print("[DB] Tablas creadas en SQLite de respaldo.", flush=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
