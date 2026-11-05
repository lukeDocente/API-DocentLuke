from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.db import get_db
from app.core.security import get_current_user, require_role
from app.models import AttendanceRecord, Device, Enrollment, Section, Student, Submission, User
from app.schemas.device import DeviceOut, LinkDeviceRequest
from app.schemas.student import StudentAttendanceOut, StudentProfileOut, StudentSubmissionOut

router = APIRouter(tags=["Estudiante y Perfil"])


@router.get("/me")
def obtener_perfil(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    nombre = None
    carnet = None
    if current_user.rol == "alumno" and current_user.student:
        nombre = current_user.student.nombre
        carnet = current_user.student.carnet

    return {
        "id": current_user.id,
        "email": current_user.email,
        "rol": current_user.rol,
        "nombre": nombre,
        "carnet": carnet,
    }


@router.get("/me/card", response_model=StudentProfileOut)
def obtener_carnet(
    current_user: User = Depends(require_role(["alumno"])),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "ESTUDIANTE_NO_ENCONTRADO", "mensaje": "Perfil de alumno no encontrado"},
        )

    # Generar token firmado para el QR del carnet
    carnet_token = security.crear_token_carnet(student.id)

    return StudentProfileOut(
        id=student.id,
        carnet=student.carnet,
        nombre=student.nombre,
        email=current_user.email,
        tel_encargado=student.tel_encargado,
        consentimiento_whatsapp=student.consentimiento_whatsapp,
        carnet_qr_token=carnet_token,
    )


@router.get("/me/attendance", response_model=list[StudentAttendanceOut])
def obtener_historial_asistencia(
    current_user: User = Depends(require_role(["alumno"])),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "ESTUDIANTE_NO_ENCONTRADO", "mensaje": "Perfil de alumno no encontrado"},
        )

    records = db.query(AttendanceRecord).filter(AttendanceRecord.student_id == student.id).order_by(AttendanceRecord.escaneado_en.desc()).all()

    return [
        StudentAttendanceOut(
            session_id=r.session_id,
            materia=r.session.section.course.nombre,
            seccion=r.session.section.nombre,
            escaneado_en=r.escaneado_en,
        )
        for r in records
    ]


@router.get("/me/submissions", response_model=list[StudentSubmissionOut])
def obtener_mis_entregas(
    current_user: User = Depends(require_role(["alumno"])),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "ESTUDIANTE_NO_ENCONTRADO", "mensaje": "Perfil de alumno no encontrado"},
        )

    submissions = db.query(Submission).filter(Submission.student_id == student.id).order_by(Submission.entregada_en.desc()).all()

    return [
        StudentSubmissionOut(
            submission_id=s.id,
            assignment_id=s.assignment_id,
            tarea=s.assignment.nombre,
            materia=s.assignment.course.nombre,
            entregada_en=s.entregada_en,
            nota=float(s.nota) if s.nota is not None else None,
            folio=s.folio,
        )
        for s in submissions
    ]


@router.post("/devices/link", response_model=DeviceOut)
def vincular_dispositivo(
    req: LinkDeviceRequest,
    current_user: User = Depends(require_role(["alumno"])),
    db: Session = Depends(get_db),
):
    # Desactivar dispositivos anteriores si solo se permite uno activo
    db.query(Device).filter(Device.user_id == current_user.id).update({"activo": False})

    nuevo_dispositivo = Device(
        user_id=current_user.id,
        huella_dispositivo=req.huella_dispositivo,
        activo=True,
    )
    db.add(nuevo_dispositivo)
    db.commit()
    db.refresh(nuevo_dispositivo)

    return DeviceOut(
        id=nuevo_dispositivo.id,
        huella_dispositivo=nuevo_dispositivo.huella_dispositivo,
        activo=nuevo_dispositivo.activo,
    )

