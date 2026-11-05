from datetime import datetime
from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    course_id: str
    nombre: str
    puntaje_max: float = 10.0


class AssignmentUpdate(BaseModel):
    abierta: bool | None = None
    nombre: str | None = None


class AssignmentOut(BaseModel):
    id: str
    course_id: str
    nombre: str
    puntaje_max: float
    abierta: bool
    created_at: datetime


class BatchSubmissionItem(BaseModel):
    token_carnet: str
    entregada_en: datetime | None = None  # Reportada por teléfono


class BatchSubmissionsRequest(BaseModel):
    items: list[BatchSubmissionItem]


class BatchSubmissionResult(BaseModel):
    token_carnet: str
    student_id: str | None = None
    carnet: str | None = None
    nombre: str | None = None
    seccion: str | None = None
    materia: str | None = None
    entregada_en: datetime
    recibida_en: datetime | None = None
    estado: str  # aceptado | duplicado | no_inscrito | invalido
    mensaje: str
    submission_id: str | None = None
    folio: str | None = None
    nota: float | None = None


class BatchSubmissionsResponse(BaseModel):
    assignment_id: str
    total: int
    procesados: list[BatchSubmissionResult]


class SubmissionGradeRequest(BaseModel):
    nota: float = Field(..., ge=0.0, le=10.0)


class SubmissionOut(BaseModel):
    id: str
    assignment_id: str
    student_id: str
    carnet: str
    nombre: str
    seccion: str | None = None
    materia: str | None = None
    entregada_en: datetime
    recibida_en: datetime
    nota: float | None = None
    folio: str

