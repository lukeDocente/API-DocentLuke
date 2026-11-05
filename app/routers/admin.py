import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core import security
from app.core.db import get_db
from app.core.security import require_role
from app.models import Course, Enrollment, Section, Student, User

router = APIRouter(prefix="/admin", tags=["Administración"])


class CreateStudentRequest(BaseModel):
    email: str = Field(..., description="Correo institucional con el que iniciará sesión el alumno")
    password: str = Field(..., min_length=6, description="Contraseña de acceso inicial")
    nombre: str = Field(..., min_length=2, description="Nombre completo del alumno")
    carnet: str = Field(..., min_length=3, description="Carnet único institucional")
    tel_encargado: str | None = Field(None, description="Número de teléfono del encargado (WhatsApp)")
    consentimiento_whatsapp: bool = Field(False, description="Autorización de notificaciones WhatsApp")
    section_id: str | None = Field(None, description="ID opcional de la sección para inscribirlo inmediatamente")


@router.post("/students", status_code=status.HTTP_201_CREATED)
def crear_alumno(
    req: CreateStudentRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Permite al Administrador registrar un alumno con su correo y contraseña para que pueda iniciar sesión."""
    email = req.email.strip().lower()
    carnet = req.carnet.strip().upper()
    nombre = req.nombre.strip()

    # 1. Validar que no exista el correo
    existente_user = db.query(User).filter(User.email == email).first()
    if existente_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "EMAIL_DUPLICADO", "mensaje": f"El correo {email} ya se encuentra registrado."},
        )

    # 2. Validar que no exista el carnet
    existente_carnet = db.query(Student).filter(Student.carnet == carnet).first()
    if existente_carnet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "CARNET_DUPLICADO", "mensaje": f"El carnet {carnet} ya está asignado a otro estudiante."},
        )

    # 3. Crear usuario con rol 'alumno'
    user = User(
        email=email,
        password_hash=security.hash_password(req.password),
        rol="alumno",
        activo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 4. Crear perfil de estudiante
    student = Student(
        user_id=user.id,
        carnet=carnet,
        nombre=nombre,
        tel_encargado=req.tel_encargado.strip() if req.tel_encargado else None,
        consentimiento_whatsapp=req.consentimiento_whatsapp,
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    # 5. Opcionalmente inscribir a sección
    seccion_info = None
    if req.section_id:
        seccion = db.query(Section).filter(Section.id == req.section_id).first()
        if seccion:
            enrollment = Enrollment(student_id=student.id, section_id=seccion.id)
            db.add(enrollment)
            db.commit()
            seccion_info = f"{seccion.course.nombre} - {seccion.nombre}"

    return {
        "status": "success",
        "mensaje": f"Alumno '{nombre}' creado exitosamente. Ya puede iniciar sesión con {email}.",
        "student": {
            "id": student.id,
            "user_id": user.id,
            "email": user.email,
            "carnet": student.carnet,
            "nombre": student.nombre,
            "tel_encargado": student.tel_encargado,
            "seccion": seccion_info,
        },
    }


@router.get("/students")
def listar_alumnos(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Lista todos los alumnos registrados para el panel de administración."""
    alumnos = db.query(Student).all()
    resultado = []
    for a in alumnos:
        u = a.user
        secciones = [
            {"id": e.section.id, "nombre": e.section.nombre, "materia": e.section.course.nombre}
            for e in a.enrollments
            if e.section and e.section.course
        ]
        resultado.append({
            "id": a.id,
            "user_id": a.user_id,
            "email": u.email if u else "",
            "carnet": a.carnet,
            "nombre": a.nombre,
            "tel_encargado": a.tel_encargado,
            "consentimiento_whatsapp": a.consentimiento_whatsapp,
            "activo": u.activo if u else False,
            "secciones": secciones,
        })
    return resultado


@router.get("/sections")
def listar_secciones_disponibles(
    current_user: User = Depends(require_role(["admin", "profesor"])),
    db: Session = Depends(get_db),
):
    """Lista todas las secciones y cursos para facilitar la inscripción."""
    secciones = db.query(Section).all()
    return [
        {
            "id": s.id,
            "nombre": s.nombre,
            "course_id": s.course_id,
            "materia": s.course.nombre if s.course else "",
            "ciclo": s.course.ciclo if s.course else "",
        }
        for s in secciones
    ]


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

