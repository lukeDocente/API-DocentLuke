from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Submission
from app.schemas.verify import FolioVerificationOut

router = APIRouter(prefix="/verify", tags=["Verificación Pública"])


@router.get("/{folio}", response_model=FolioVerificationOut)
def verificar_constancia(folio: str, db: Session = Depends(get_db)):
    sub = db.query(Submission).filter(Submission.folio == folio).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "FOLIO_INEXISTENTE", "mensaje": "La constancia con este folio no existe o es inválida"},
        )

    return FolioVerificationOut(
        valido=True,
        folio=sub.folio,
        alumno=sub.student.nombre,
        carnet=sub.student.carnet,
        tarea=sub.assignment.nombre,
        materia=sub.assignment.course.nombre,
        profesor=sub.assignment.course.profesor.email,
        entregada_en=sub.entregada_en,
        nota=float(sub.nota) if sub.nota is not None else None,
        puntaje_max=float(sub.assignment.puntaje_max),
    )

