from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import security
from app.core.db import get_db
from app.core.security import require_role
from app.models import Assignment, AttendanceRecord, AttendanceSession, Enrollment, Section, Student, Submission, User

router = APIRouter(prefix="/sync", tags=["Sincronización Fuera de Línea"])


class OfflineSubmissionItem(BaseModel):
    idempotency_id: str
    assignment_id: str
    token_carnet: str
    entregada_en: datetime


class OfflineAttendanceItem(BaseModel):
    idempotency_id: str
    session_id: str
    student_id_or_token: str
    escaneado_en: datetime
    device_id: str | None = None


class BatchSyncRequest(BaseModel):
    submissions: list[OfflineSubmissionItem] = []
    attendances: list[OfflineAttendanceItem] = []


@router.post("/batch")
def sincronizar_lote(
    req: BatchSyncRequest,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    ahora_servidor = datetime.now(timezone.utc)
    res_submissions = []
    res_attendances = []

    # 1. Sincronizar entregas
    for item in req.submissions:
        tarea = db.query(Assignment).filter(Assignment.id == item.assignment_id).first()
        student_id = security.validar_token_carnet(item.token_carnet)

        if not tarea or not student_id:
            res_submissions.append({
                "idempotency_id": item.idempotency_id,
                "estado": "error",
                "mensaje": "Tarea inexistente o token de carnet inválido",
            })
            continue

        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            res_submissions.append({
                "idempotency_id": item.idempotency_id,
                "estado": "error",
                "mensaje": "Estudiante no encontrado",
            })
            continue

        existente = db.query(Submission).filter(
            Submission.assignment_id == item.assignment_id,
            Submission.student_id == student.id,
        ).first()

        if existente:
            res_submissions.append({
                "idempotency_id": item.idempotency_id,
                "estado": "duplicado",
                "submission_id": existente.id,
                "folio": existente.folio,
                "mensaje": "Entrega ya existía",
            })
        else:
            nueva = Submission(
                assignment_id=item.assignment_id,
                student_id=student.id,
                entregada_en=item.entregada_en,
                recibida_en=ahora_servidor,
                folio=str(uuid.uuid4()),
            )
            db.add(nueva)
            db.commit()
            db.refresh(nueva)
            res_submissions.append({
                "idempotency_id": item.idempotency_id,
                "estado": "creado",
                "submission_id": nueva.id,
                "folio": nueva.folio,
                "mensaje": "Sincronizado correctamente",
            })

    # 2. Sincronizar asistencias
    for att in req.attendances:
        sesion = db.query(AttendanceSession).filter(AttendanceSession.id == att.session_id).first()
        if not sesion:
            res_attendances.append({
                "idempotency_id": att.idempotency_id,
                "estado": "error",
                "mensaje": "Sesión inexistente",
            })
            continue

        # Intentar validar si vino token o direct student_id
        student_id = security.validar_token_carnet(att.student_id_or_token) or att.student_id_or_token
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            res_attendances.append({
                "idempotency_id": att.idempotency_id,
                "estado": "error",
                "mensaje": "Alumno no encontrado",
            })
            continue

        existente_att = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == att.session_id,
            AttendanceRecord.student_id == student.id,
        ).first()

        if existente_att:
            res_attendances.append({
                "idempotency_id": att.idempotency_id,
                "estado": "duplicado",
                "record_id": existente_att.id,
            })
        else:
            dev = None
            if att.device_id:
                dev = db.query(Device).filter(Device.id == att.device_id).first()
                if not dev:
                    dev = db.query(Device).filter(Device.huella_dispositivo == att.device_id).first()

            rec = AttendanceRecord(
                session_id=att.session_id,
                student_id=student.id,
                escaneado_en=att.escaneado_en,
                device_id=dev.id if dev else None,
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            res_attendances.append({
                "idempotency_id": att.idempotency_id,
                "estado": "creado",
                "record_id": rec.id,
            })

    return {
        "submissions": res_submissions,
        "attendances": res_attendances,
        "sincronizado_en": ahora_servidor,
    }

