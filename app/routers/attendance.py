from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.core import security
from app.core.config import settings
from app.core.db import get_db
from app.core.security import require_role
from app.models import AttendanceRecord, AttendanceSession, Device, Enrollment, Section, Student, User
from app.schemas.attendance import AttendanceRecordOut, QRResponse, ScanAttendanceRequest, SessionCreate, SessionOut

router = APIRouter(prefix="/attendance", tags=["Asistencia"])


class ScanCarnetRequest(BaseModel):
    token_carnet: str
    escaneado_en: datetime | None = None


class ManualAttendanceRequest(BaseModel):
    student_id: str
    presente: bool = True


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def abrir_sesion(
    req: SessionCreate,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    seccion = db.query(Section).filter(Section.id == req.section_id).first()
    if not seccion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SECCION_NO_ENCONTRADA", "mensaje": "La sección especificada no existe"},
        )
    if current_user.rol == "profesor" and seccion.course.profesor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "NO_AUTORIZADO", "mensaje": "No tienes acceso a esta sección"},
        )

    # Crear nueva sesión abierta
    sesion = AttendanceSession(section_id=req.section_id)
    db.add(sesion)
    db.commit()
    db.refresh(sesion)

    return SessionOut(
        id=sesion.id,
        section_id=sesion.section_id,
        abierta_en=sesion.abierta_en,
        cerrada_en=sesion.cerrada_en,
    )


@router.get("/sessions/{id}/qr", response_model=QRResponse)
def obtener_qr_sesion(
    id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    sesion = db.query(AttendanceSession).filter(AttendanceSession.id == id).first()
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SESION_NO_ENCONTRADA", "mensaje": "La sesión no existe"},
        )
    if sesion.cerrada_en is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "SESION_CERRADA", "mensaje": "La sesión de asistencia ya está cerrada"},
        )

    token = security.crear_token_asistencia(sesion.id)
    return QRResponse(
        session_id=sesion.id,
        token=token,
        ventana_segundos=settings.qr_window_seconds,
    )


@router.patch("/sessions/{id}/close", response_model=SessionOut)
def cerrar_sesion(
    id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    sesion = db.query(AttendanceSession).filter(AttendanceSession.id == id).first()
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SESION_NO_ENCONTRADA", "mensaje": "La sesión no existe"},
        )

    if sesion.cerrada_en is None:
        sesion.cerrada_en = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sesion)

    return SessionOut(
        id=sesion.id,
        section_id=sesion.section_id,
        abierta_en=sesion.abierta_en,
        cerrada_en=sesion.cerrada_en,
    )


@router.get("/sessions/{id}/records", response_model=list[AttendanceRecordOut])
def listar_asistentes_sesion(
    id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    sesion = db.query(AttendanceSession).filter(AttendanceSession.id == id).first()
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SESION_NO_ENCONTRADA", "mensaje": "La sesión no existe"},
        )

    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == id).order_by(AttendanceRecord.escaneado_en.desc()).all()

    return [
        AttendanceRecordOut(
            id=r.id,
            student_id=r.student_id,
            carnet=r.student.carnet,
            nombre=r.student.nombre,
            escaneado_en=r.escaneado_en,
            device_id=r.device_id,
        )
        for r in records
    ]


@router.get("/sessions/{id}/roster")
def obtener_roster_asistencia(
    id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    """Devuelve la lista completa de alumnos inscritos en la sección de la sesión,
    indicando quiénes ya tienen asistencia registrada y quiénes están ausentes."""
    sesion = db.query(AttendanceSession).filter(AttendanceSession.id == id).first()
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SESION_NO_ENCONTRADA", "mensaje": "La sesión no existe"},
        )

    # 1. Alumnos inscritos
    enrollments = db.query(Enrollment).filter(Enrollment.section_id == sesion.section_id).all()
    # 2. Asistencias ya marcadas
    records = {
        r.student_id: r.escaneado_en
        for r in db.query(AttendanceRecord).filter(AttendanceRecord.session_id == id).all()
    }

    roster = []
    for e in enrollments:
        s = e.student
        if not s:
            continue
        presente = s.id in records
        roster.append({
            "student_id": s.id,
            "carnet": s.carnet,
            "nombre": s.nombre,
            "presente": presente,
            "escaneado_en": records.get(s.id),
        })

    # Ordenar alfabéticamente por nombre
    roster.sort(key=lambda x: x["nombre"])

    total_alumnos = len(roster)
    total_presentes = sum(1 for x in roster if x["presente"])

    return {
        "session_id": sesion.id,
        "section_id": sesion.section_id,
        "seccion_nombre": sesion.section.nombre if sesion.section else "",
        "materia": sesion.section.course.nombre if (sesion.section and sesion.section.course) else "",
        "abierta_en": sesion.abierta_en,
        "cerrada_en": sesion.cerrada_en,
        "total_alumnos": total_alumnos,
        "total_presentes": total_presentes,
        "alumnos": roster,
    }


@router.post("/sessions/{id}/scan-student")
def escanear_carnet_docente(
    id: str,
    req: ScanCarnetRequest,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    """El docente escanea con su cámara el QR del carnet del alumno para registrar la asistencia."""
    sesion = db.query(AttendanceSession).filter(AttendanceSession.id == id).first()
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SESION_NO_ENCONTRADA", "mensaje": "La sesión no existe"},
        )
    if sesion.cerrada_en is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "SESION_CERRADA", "mensaje": "La sesión de asistencia ya está cerrada"},
        )

    # 1. Resolver el estudiante a partir del token o carnet
    token = req.token_carnet.strip()
    student_id = security.validar_token_carnet(token)

    student = None
    if student_id:
        student = db.query(Student).filter(Student.id == student_id).first()

    # Si no tiene firma válida, buscar directamente por NIE o ID
    if not student:
        student = db.query(Student).filter((Student.carnet == token) | (Student.id == token)).first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "ALUMNO_NO_ENCONTRADO", "mensaje": f"No se encontró ningún estudiante con el código escaneado"},
        )

    # 2. Validar que esté inscrito en la sección
    inscrito = db.query(Enrollment).filter(
        Enrollment.student_id == student.id,
        Enrollment.section_id == sesion.section_id,
    ).first()
    if not inscrito:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "codigo": "NO_INSCRITO",
                "mensaje": f"El alumno {student.nombre} (NIE: {student.carnet}) no está matriculado en esta sección",
            },
        )

    # 3. Comprobar si ya está registrada
    existente = db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == sesion.id,
        AttendanceRecord.student_id == student.id,
    ).first()

    total_presentes = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == sesion.id).count()

    if existente:
        return {
            "estado": "ya_registrada",
            "mensaje": f"Asistencia previamente registrada a las {existente.escaneado_en.strftime('%H:%M:%S')}",
            "student_id": student.id,
            "carnet": student.carnet,
            "alumno": student.nombre,
            "escaneado_en": existente.escaneado_en,
            "total_presentes": total_presentes,
        }

    # 4. Registrar asistencia con hora UTC
    ahora_utc = req.escaneado_en or datetime.now(timezone.utc)
    registro = AttendanceRecord(
        session_id=sesion.id,
        student_id=student.id,
        escaneado_en=ahora_utc,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)

    total_presentes += 1

    return {
        "estado": "confirmado",
        "mensaje": "¡Asistencia registrada exitosamente!",
        "student_id": student.id,
        "carnet": student.carnet,
        "alumno": student.nombre,
        "escaneado_en": registro.escaneado_en,
        "total_presentes": total_presentes,
    }


@router.post("/sessions/{id}/manual-attendance")
def marcar_asistencia_manual(
    id: str,
    req: ManualAttendanceRequest,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    """Permite al docente marcar o desmarcar la asistencia manualmente si el alumno no porta su carnet."""
    sesion = db.query(AttendanceSession).filter(AttendanceSession.id == id).first()
    if not sesion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada")

    student = db.query(Student).filter(Student.id == req.student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alumno no encontrado")

    existente = db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == sesion.id,
        AttendanceRecord.student_id == student.id,
    ).first()

    if req.presente and not existente:
        registro = AttendanceRecord(
            session_id=sesion.id,
            student_id=student.id,
            escaneado_en=datetime.now(timezone.utc),
        )
        db.add(registro)
        db.commit()
        db.refresh(registro)
        return {"estado": "presente", "mensaje": f"Asistencia marcada manualmente para {student.nombre}"}
    elif not req.presente and existente:
        db.delete(existente)
        db.commit()
        return {"estado": "ausente", "mensaje": f"Asistencia retirada para {student.nombre}"}

    return {"estado": "sin_cambio", "mensaje": "Estado sin modificaciones"}


@router.post("/scan", status_code=status.HTTP_200_OK)
def registrar_asistencia(
    req: ScanAttendanceRequest,
    current_user: User = Depends(require_role(["alumno"])),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    # 1. Validar token QR dinámico
    sesion_id = security.validar_token_asistencia(req.token)
    if not sesion_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "QR_INVALIDO_O_EXPIRADO", "mensaje": "El código QR ha expirado o no es válido"},
        )

    # 2. Verificar sesión abierta
    sesion = db.query(AttendanceSession).filter(AttendanceSession.id == sesion_id).first()
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SESION_NO_EXISTE", "mensaje": "La sesión de asistencia no existe"},
        )
    if sesion.cerrada_en is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "SESION_CERRADA", "mensaje": "La sesión de asistencia ya fue cerrada por el profesor"},
        )

    # 3. Obtener perfil de alumno
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "ALUMNO_NO_REGISTRADO", "mensaje": "No se encontró el perfil de estudiante"},
        )

    # 4. Validar dispositivo si el alumno tiene uno vinculado
    vinculo = None
    if req.huella_dispositivo:
        vinculo = db.query(Device).filter(Device.user_id == current_user.id, Device.activo.is_(True)).first()
        if vinculo and vinculo.huella_dispositivo != req.huella_dispositivo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"codigo": "DISPOSITIVO_NO_VINCULADO", "mensaje": "Este dispositivo no coincide con el registrado para esta cuenta"},
            )

    # 5. Comprobar que esté inscrito en la sección
    inscrito = db.query(Enrollment).filter(
        Enrollment.student_id == student.id,
        Enrollment.section_id == sesion.section_id,
    ).first()
    if not inscrito:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "NO_INSCRITO", "mensaje": "El alumno no está inscrito en esta sección"},
        )

    # 6. Comprobar duplicado
    existente = db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == sesion.id,
        AttendanceRecord.student_id == student.id,
    ).first()
    if existente:
        return {
            "estado": "ya_registrada",
            "mensaje": f"Asistencia previamente registrada a las {existente.escaneado_en.strftime('%H:%M:%S')}",
            "escaneado_en": existente.escaneado_en,
        }

    # 7. Registrar asistencia con hora UTC del servidor
    ahora_utc = datetime.now(timezone.utc)
    registro = AttendanceRecord(
        session_id=sesion.id,
        student_id=student.id,
        escaneado_en=ahora_utc,
        device_id=vinculo.id if vinculo else None,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)

    return {
        "estado": "confirmado",
        "mensaje": "Asistencia registrada correctamente",
        "alumno": student.nombre,
        "carnet": student.carnet,
        "escaneado_en": registro.escaneado_en,
    }

