"""Script de inicialización de datos de prueba (Seed)."""
from app.core.db import SessionLocal, init_db
from app.core import security
from app.models import Assignment, Course, Enrollment, Section, Student, User


def seed():
    init_db()
    db = SessionLocal()
    try:
        # 1. Profesor
        profesor = db.query(User).filter(User.email == "profesor@luke.edu").first()
        if not profesor:
            profesor = User(
                email="profesor@luke.edu",
                password_hash=security.hash_password("Profesor123*"),
                rol="profesor",
                activo=True,
            )
            db.add(profesor)
            db.commit()
            db.refresh(profesor)
            print("Creado profesor: profesor@luke.edu / Profesor123*")

        # 2. Alumno
        alumno_user = db.query(User).filter(User.email == "alumno@luke.edu").first()
        if not alumno_user:
            alumno_user = User(
                email="alumno@luke.edu",
                password_hash=security.hash_password("Alumno123*"),
                rol="alumno",
                activo=True,
            )
            db.add(alumno_user)
            db.commit()
            db.refresh(alumno_user)

            student = Student(
                user_id=alumno_user.id,
                carnet="2026-ALU-001",
                nombre="Carlos Mendoza",
                tel_encargado="+50255512345",
                consentimiento_whatsapp=True,
            )
            db.add(student)
            db.commit()
            db.refresh(student)
            print("Creado alumno: alumno@luke.edu / Alumno123* (Carnet: 2026-ALU-001)")
        else:
            student = db.query(Student).filter(Student.user_id == alumno_user.id).first()

        # 3. Admin
        admin_user = db.query(User).filter(User.email == "admin@luke.edu").first()
        if not admin_user:
            admin_user = User(
                email="admin@luke.edu",
                password_hash=security.hash_password("Admin123*"),
                rol="admin",
                activo=True,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print("Creado admin: admin@luke.edu / Admin123*")

        # 4. Curso y Sección
        curso = db.query(Course).filter(Course.nombre == "Matemáticas Discretas").first()
        if not curso:
            curso = Course(
                nombre="Matemáticas Discretas",
                profesor_id=profesor.id,
                ciclo="2026-1",
            )
            db.add(curso)
            db.commit()
            db.refresh(curso)

            seccion = Section(course_id=curso.id, nombre="Sección A")
            db.add(seccion)
            db.commit()
            db.refresh(seccion)

            # Inscribir alumno
            if student:
                inscripcion = Enrollment(student_id=student.id, section_id=seccion.id)
                db.add(inscripcion)
                db.commit()

            # Tarea
            tarea = Assignment(
                course_id=curso.id,
                nombre="Laboratorio 1 - Grafos",
                puntaje_max=10.0,
                abierta=True,
            )
            db.add(tarea)
            db.commit()
            print("Creado curso 'Matemáticas Discretas', Sección A, Tarea 'Laboratorio 1 - Grafos'")

        print("Base de datos inicializada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

