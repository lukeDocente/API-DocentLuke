import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.db import get_db
from app.core.security import require_role
from app.models import Course, Enrollment, Section, Student, User

router = APIRouter(prefix="/admin", tags=["Administración"])


@router.post("/import")
async def importar_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Importa alumnos, cursos, secciones y encargados mediante un archivo CSV.
    Columnas esperadas:
    email,password,nombre,carnet,tel_encargado,curso,seccion,ciclo
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "FORMATO_INVALIDO", "mensaje": "El archivo debe ser un CSV"},
        )

    contenido = await file.read()
    texto = contenido.decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(texto))

    procesados = 0
    errores = []

    for fila_num, fila in enumerate(lector, start=2):
        try:
            email = fila.get("email", "").strip().lower()
            password = fila.get("password", "Alumno123*").strip()
            nombre = fila.get("nombre", "").strip()
            carnet = fila.get("carnet", "").strip()
            tel_encargado = fila.get("tel_encargado", "").strip() or None
            curso_nombre = fila.get("curso", "").strip()
            seccion_nombre = fila.get("seccion", "").strip()
            ciclo = fila.get("ciclo", "2026-1").strip()

            if not email or not carnet or not nombre:
                errores.append(f"Fila {fila_num}: faltan campos obligatorios (email, carnet o nombre)")
                continue

            # 1. Crear o buscar usuario alumno
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    email=email,
                    password_hash=security.hash_password(password),
                    rol="alumno",
                    activo=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            # 2. Crear o buscar alumno
            student = db.query(Student).filter(Student.user_id == user.id).first()
            if not student:
                student = Student(
                    user_id=user.id,
                    carnet=carnet,
                    nombre=nombre,
                    tel_encargado=tel_encargado,
                )
                db.add(student)
                db.commit()
                db.refresh(student)

            # 3. Asignar curso y sección si se especificaron
            if curso_nombre and seccion_nombre:
                curso = db.query(Course).filter(Course.nombre == curso_nombre).first()
                if not curso:
                    # Crear curso asignado temporalmente al admin que lo importa
                    curso = Course(
                        nombre=curso_nombre,
                        profesor_id=current_user.id,
                        ciclo=ciclo,
                    )
                    db.add(curso)
                    db.commit()
                    db.refresh(curso)

                seccion = db.query(Section).filter(Section.course_id == curso.id, Section.nombre == seccion_nombre).first()
                if not seccion:
                    seccion = Section(course_id=curso.id, nombre=seccion_nombre)
                    db.add(seccion)
                    db.commit()
                    db.refresh(seccion)

                # Inscribir
                inscrito = db.query(Enrollment).filter(
                    Enrollment.student_id == student.id,
                    Enrollment.section_id == seccion.id,
                ).first()
                if not inscrito:
                    enrollment = Enrollment(student_id=student.id, section_id=seccion.id)
                    db.add(enrollment)
                    db.commit()

            procesados += 1
        except Exception as e:
            db.rollback()
            errores.append(f"Fila {fila_num}: error procesando - {str(e)}")

    return {
        "procesados": procesados,
        "errores": errores,
    }

