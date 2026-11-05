from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_role
from app.models import GradeAudit, Submission, User
from app.schemas.assignment import SubmissionGradeRequest, SubmissionOut

router = APIRouter(prefix="/submissions", tags=["Calificaciones y Entregas"])


@router.patch("/{id}/grade", response_model=SubmissionOut)
def calificar_entrega(
    id: str,
    req: SubmissionGradeRequest,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == id).first()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "ENTREGA_NO_ENCONTRADA", "mensaje": "La entrega no existe"},
        )

    # Validar que el profesor es el dueño del curso
    if current_user.rol == "profesor" and submission.assignment.course.profesor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "NO_AUTORIZADO", "mensaje": "No tienes permiso para calificar esta entrega"},
        )

    nota_anterior = float(submission.nota) if submission.nota is not None else None
    submission.nota = req.nota

    # Auditoría del cambio de nota
    audit = GradeAudit(
        submission_id=submission.id,
        usuario_id=current_user.id,
        nota_anterior=nota_anterior,
        nota_nueva=req.nota,
        cambiado_en=datetime.now(timezone.utc),
    )
    db.add(audit)
    db.commit()
    db.refresh(submission)

    return SubmissionOut(
        id=submission.id,
        assignment_id=submission.assignment_id,
        student_id=submission.student_id,
        carnet=submission.student.carnet,
        nombre=submission.student.nombre,
        materia=submission.assignment.course.nombre,
        entregada_en=submission.entregada_en,
        recibida_en=submission.recibida_en,
        nota=float(submission.nota),
        folio=submission.folio,
    )

