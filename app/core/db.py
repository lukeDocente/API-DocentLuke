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
    # Timeout corto para no demorar el inicio
    connect_args["connect_timeout"] = 4

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


ESTUDIANTES_5TO = [
    ("10351778", "ARAUJO VALLECIOS, DOMINIC MATEO"),
    ("10351712", "AREVALO MOLINA, CRISTIAN ALEJANDRO"),
    ("10387707", "AREVALO PEREZ, ASHLEY SOFIA"),
    ("10491628", "AREVALO RAMIREZ, MARIANA VALENTINA"),
    ("10151625", "BRITO RAMIREZ, DIANA VIOLETA"),
    ("10351747", "CARTAGENA SIERRA, RACHEL ABIGAIL"),
    ("10351757", "CHAVEZ PINTE, JACQUELINE ARIANA"),
    ("10151643", "CUADRA VASQUEZ, JOSHUA CALEB"),
    ("10351735", "ELIAS SIERRA, ALEXIA VALENTINA"),
    ("10351824", "FUNES AMAS, BETZY ANALYZ"),
    ("10512956", "GALICIA CORTEZ, CRISTIAN ENRIQUE"),
    ("10151692", "GOMEZ CAMPOS, HENDRICK JAFET"),
    ("10351721", "HERRERA AREVALO, LEONARDO ISAAC"),
    ("10512973", "LOPEZ ESCOBAR, JENNIFER CAROLINA"),
    ("10151705", "LUE HURTADO, SAUL ENRIQUE"),
    ("10351813", "MASIN SIERRA, MONICA REBECA"),
    ("10457205", "MIRANDA AQUINO, STEPHANIE BEATRIZ"),
    ("10205961", "PEREZ HURTADO, KELVIN STEVEN"),
    ("10387675", "PEREZ TINO, BERNARDO JOAQUIN"),
    ("10371453", "ROJAS ESQUINA, JONATHAN STANLEY"),
    ("10351800", "ROMERO ESCOBAR, MIGUEL ARMANDO"),
    ("10205958", "SANDOVAL BARRIENTOS, VICTOR MATIAS"),
    ("10351684", "SAYES MATE, OSCAR ARISTIDES"),
    ("10156124", "SIERRA JIMENEZ, AXEL FRANCISCO"),
    ("10178370", "VALDEZ ACEITUNO, YEIMY MELISSA"),
]


def seed_admin(db: Session):
    try:
        from app.models import Assignment, Course, Enrollment, Section, Student, User
        from app.core import security

        # 1. Administrador general
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
            db.refresh(admin)
            print(f"[DB] Administrador sembrado exitosamente: {admin_email}", flush=True)
        else:
            if admin.rol != "admin" or not security.verify_password("Luke#solis", admin.password_hash):
                admin.rol = "admin"
                admin.password_hash = security.hash_password("Luke#solis")
                admin.activo = True
                db.commit()

        # 2. Docente inicial (opcional)
        docente = db.query(User).filter(User.email == "profesor@luke.edu").first()
        if not docente:
            docente = User(
                email="profesor@luke.edu",
                password_hash=security.hash_password("Profesor123*"),
                rol="profesor",
                activo=True,
            )
            db.add(docente)
            db.commit()
            db.refresh(docente)

        # 3. Curso Oficial "5° Grado - Educación Básica"
        curso_nombre = "5° Grado - Educación Básica"
        curso = db.query(Course).filter(Course.nombre == curso_nombre).first()
        if not curso:
            curso = Course(
                nombre=curso_nombre,
                profesor_id=admin.id,
                ciclo="2026",
            )
            db.add(curso)
            db.commit()
            db.refresh(curso)
            print(f"[DB] Curso sembrado: {curso.nombre}", flush=True)

        # 4. Sección A
        seccion_nombre = "Sección A"
        seccion = db.query(Section).filter(Section.course_id == curso.id, Section.nombre == seccion_nombre).first()
        if not seccion:
            seccion = Section(
                course_id=curso.id,
                nombre=seccion_nombre,
            )
            db.add(seccion)
            db.commit()
            db.refresh(seccion)
            print(f"[DB] Sección sembrada: {seccion.nombre}", flush=True)

        # 5. Tarea Inicial para pruebas inmediatas de escaneo y calificación
        tarea_nombre = "Tarea 1 - Revisión de Cuaderno"
        tarea = db.query(Assignment).filter(Assignment.course_id == curso.id, Assignment.nombre == tarea_nombre).first()
        if not tarea:
            tarea = Assignment(
                course_id=curso.id,
                nombre=tarea_nombre,
                puntaje_max=10.0,
                abierta=True,
            )
            db.add(tarea)
            db.commit()
            print(f"[DB] Tarea inicial sembrada: {tarea.nombre}", flush=True)

        # 6. Sembrar los 25 alumnos oficiales de 5°.xlsx
        inscritos_count = 0
        hash_alumno = security.hash_password("Alumno123*")
        for nie, nombre in ESTUDIANTES_5TO:
            email_est = f"{nie}@estudiante.edu.sv"

            user_est = db.query(User).filter(User.email == email_est).first()
            if not user_est:
                user_est = User(
                    email=email_est,
                    password_hash=hash_alumno,
                    rol="alumno",
                    activo=True,
                )
                db.add(user_est)
                db.commit()
                db.refresh(user_est)

            student = db.query(Student).filter(Student.carnet == nie).first()
            if not student:
                student = Student(
                    user_id=user_est.id,
                    carnet=nie,
                    nombre=nombre,
                )
                db.add(student)
                db.commit()
                db.refresh(student)
            else:
                student.nombre = nombre
                db.commit()

            enrollment = db.query(Enrollment).filter(
                Enrollment.student_id == student.id,
                Enrollment.section_id == seccion.id,
            ).first()
            if not enrollment:
                enrollment = Enrollment(student_id=student.id, section_id=seccion.id)
                db.add(enrollment)
                db.commit()
                inscritos_count += 1

        if inscritos_count > 0:
            print(f"[DB] {inscritos_count} alumnos sembrados y matriculados en 5° Grado Sección A.", flush=True)

    except Exception as e:
        db.rollback()
        print(f"[DB] Error sembrando datos escolares iniciales: {e}", file=sys.stderr, flush=True)
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
