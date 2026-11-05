from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.db import get_db
from app.core.security import require_role
from app.models import AttendanceRecord, AttendanceSession, Device, Enrollment, Section, Student, User
from app.schemas.attendance import AttendanceRecordOut, QRResponse, ScanAttendanceRequest, SessionCreate, SessionOut

router = APIRouter(prefix="/attendance", tags=["Asistencia"])


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

