from datetime import datetime
from pydantic import BaseModel


class StudentProfileOut(BaseModel):
    id: str
    carnet: str
    nombre: str
    email: str
    tel_encargado: str | None = None
    consentimiento_whatsapp: bool
    carnet_qr_token: str


class StudentAttendanceOut(BaseModel):
    session_id: str
    materia: str
    seccion: str
    escaneado_en: datetime


class StudentSubmissionOut(BaseModel):
    submission_id: str
    assignment_id: str
    tarea: str
    materia: str
    entregada_en: datetime
    nota: float | None = None
    folio: str

