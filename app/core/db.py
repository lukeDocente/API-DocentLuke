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


def seed_admin(db: Session):
    try:
        from app.models import User
        from app.core import security
        admin_email = "lukesolis@edu.sv"
        admin = db.query(User).filter(User.email == admin_email).first()
        if not admin:
            admin = User(
                email=admin_email,
                password_hash=security.hash_password("Luke#solis"),
                rol="admin",
                activo=True,
            )
            db.add(admin)
            db.commit()
            print(f"[DB] Administrador sembrado exitosamente: {admin_email}", flush=True)
        else:
            if admin.rol != "admin" or not security.verify_password("Luke#solis", admin.password_hash):
                admin.rol = "admin"
                admin.password_hash = security.hash_password("Luke#solis")
                admin.activo = True
                db.commit()
                print(f"[DB] Administrador verificado y actualizado: {admin_email}", flush=True)
    except Exception as e:
        db.rollback()
        print(f"[DB] Error sembrando administrador inicial: {e}", file=sys.stderr, flush=True)
    finally:
        db.close()


def init_db():
    global engine, SessionLocal
    try:
        print(f"[DB] Conectando y creando tablas con URL: {engine.url.render_as_string(hide_password=True)}", flush=True)
        Base.metadata.create_all(bind=engine)
        print("[DB] Tablas inicializadas exitosamente.", flush=True)
        seed_admin(SessionLocal())
    except Exception as e:
        print(f"[DB] ADVERTENCIA: No se pudo conectar a la base de datos remota ({e}).", file=sys.stderr, flush=True)
        print("[DB] Activando base de datos SQLite local de respaldo para mantener el servicio activo...", file=sys.stderr, flush=True)
        engine = create_engine("sqlite:///./asistencia.db", connect_args={"check_same_thread": False})
        SessionLocal.configure(bind=engine)
        Base.metadata.create_all(bind=engine)
        print("[DB] Tablas creadas en SQLite de respaldo.", flush=True)
        seed_admin(SessionLocal())


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
