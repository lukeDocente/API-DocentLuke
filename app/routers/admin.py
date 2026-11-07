import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
import openpyxl

from app.core import security
from app.core.db import get_db
from app.core.security import require_role
from app.models import Course, Enrollment, Section, Student, User
from app.services.carnet import generar_carnet_png

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
    current_user: User = Depends(require_role(["admin", "profesor"])),
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

    token_carnet = security.crear_token_carnet(student.id)

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
            "token_carnet": token_carnet,
        },
    }


@router.get("/students/{id}/carnet")
def descargar_carnet_estudiante(
    id: str,
    current_user: User = Depends(require_role(["admin", "profesor"])),
    db: Session = Depends(get_db),
):
    """Genera y descarga directamente la imagen oficial del carnet estudiantil con código QR."""
    student = db.query(Student).filter(Student.id == id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "ALUMNO_NO_ENCONTRADO", "mensaje": "Estudiante no encontrado"},
        )

    seccion_str = "Sección General"
    institucion_str = 'CENTRO ESCOLAR "JOSE QUETGLAS"'
    if student.enrollments:
        sec = student.enrollments[0].section
        if sec and sec.course:
            seccion_str = f"{sec.course.nombre} - {sec.nombre}"

    png_bytes = generar_carnet_png(
        student_id=student.id,
        carnet=student.carnet,
        nombre=student.nombre,
        institucion=institucion_str,
        seccion=seccion_str,
    )

    clean_name = student.carnet.replace(" ", "_")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="Carnet_{clean_name}.png"'},
    )


@router.get("/students")
def listar_alumnos(
    current_user: User = Depends(require_role(["admin", "profesor"])),
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
async def importar_alumnos_archivo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(["admin", "profesor"])),
    db: Session = Depends(get_db),
):
    """Importa alumnos desde un archivo Excel (.xlsx) oficial del MINEDUCYT o un archivo CSV."""
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".xlsx") or filename_lower.endswith(".csv")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "FORMATO_INVALIDO", "mensaje": "El archivo debe ser un Excel (.xlsx) o CSV (.csv)"},
        )

    contenido = await file.read()
    procesados = 0
    errores = []

    if filename_lower.endswith(".xlsx"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(contenido))
            sheet = wb.active

            # Detectar si es formato oficial MINEDUCYT (e.g. 5°.xlsx)
            curso_nombre = "5° Grado - Educación Básica"
            seccion_nombre = "Sección A"
            ciclo = "2026"

            # Intentar leer metadatos de las primeras filas si existen
            for r in range(1, 10):
                c1 = str(sheet.cell(row=r, column=1).value or "")
                c4 = str(sheet.cell(row=r, column=4).value or "")
                if "servicio educativo" in c1.lower() and c4:
                    curso_nombre = c4.strip()
                elif "sección" in c1.lower() and c4:
                    seccion_nombre = c4.strip()
                elif "año lectivo" in c1.lower() and c4:
                    ciclo = str(sheet.cell(row=r, column=4).value or "2026").strip()

            # Buscar o crear Curso
            curso = db.query(Course).filter(Course.nombre == curso_nombre).first()
            if not curso:
                curso = Course(nombre=curso_nombre, profesor_id=current_user.id, ciclo=ciclo)
                db.add(curso)
                db.commit()
                db.refresh(curso)

            # Buscar o crear Sección
            seccion = db.query(Section).filter(Section.course_id == curso.id, Section.nombre == seccion_nombre).first()
            if not seccion:
                seccion = Section(course_id=curso.id, nombre=seccion_nombre)
                db.add(seccion)
                db.commit()
                db.refresh(seccion)

            # Buscar la fila de encabezados o estudiantes
            start_row = 1
            for r in range(1, min(20, sheet.max_row + 1)):
                val1 = str(sheet.cell(row=r, column=1).value or "").lower()
                val2 = str(sheet.cell(row=r, column=2).value or "").lower()
                if "no." in val1 or "nie" in val2:
                    start_row = r + 1
                    break

            for r in range(start_row, sheet.max_row + 1):
                c1 = sheet.cell(row=r, column=1).value
                c2 = sheet.cell(row=r, column=2).value
                c3 = sheet.cell(row=r, column=3).value

                if not c2 or not c3:
                    continue

                carnet_str = str(c2).strip()
                nombre_str = str(c3).strip()
                email_estudiante = f"{carnet_str}@estudiante.edu.sv"

                try:
                    # 1. Crear o buscar usuario
                    user = db.query(User).filter(User.email == email_estudiante).first()
                    if not user:
                        user = User(
                            email=email_estudiante,
                            password_hash=security.hash_password("Alumno123*"),
                            rol="alumno",
                            activo=True,
                        )
                        db.add(user)
                        db.commit()
                        db.refresh(user)

                    # 2. Crear o buscar estudiante
                    student = db.query(Student).filter(Student.carnet == carnet_str).first()
                    if not student:
                        student = Student(
                            user_id=user.id,
                            carnet=carnet_str,
                            nombre=nombre_str,
                        )
                        db.add(student)
                        db.commit()
                        db.refresh(student)
                    else:
                        student.nombre = nombre_str
                        db.commit()

                    # 3. Matricular
                    inscrito = db.query(Enrollment).filter(
                        Enrollment.student_id == student.id,
                        Enrollment.section_id == seccion.id,
                    ).first()
                    if not inscrito:
                        enrollment = Enrollment(student_id=student.id, section_id=seccion.id)
                        db.add(enrollment)
                        db.commit()

                    procesados += 1
                except Exception as ex:
                    db.rollback()
                    errores.append(f"Fila {r}: {ex}")

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"codigo": "ERROR_EXCEL", "mensaje": f"No se pudo procesar el Excel: {e}"},
            )

    else:
        # Procesamiento de archivo CSV
        texto = contenido.decode("utf-8-sig")
        lector = csv.DictReader(io.StringIO(texto))

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

                if curso_nombre and seccion_nombre:
                    curso = db.query(Course).filter(Course.nombre == curso_nombre).first()
                    if not curso:
                        curso = Course(nombre=curso_nombre, profesor_id=current_user.id, ciclo=ciclo)
                        db.add(curso)
                        db.commit()
                        db.refresh(curso)

                    seccion = db.query(Section).filter(Section.course_id == curso.id, Section.nombre == seccion_nombre).first()
                    if not seccion:
                        seccion = Section(course_id=curso.id, nombre=seccion_nombre)
                        db.add(seccion)
                        db.commit()
                        db.refresh(seccion)

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

