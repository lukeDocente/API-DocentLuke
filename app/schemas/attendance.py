from datetime import datetime
from pydantic import BaseModel


class SessionCreate(BaseModel):
    section_id: str


class SessionOut(BaseModel):
    id: str
    section_id: str
    abierta_en: datetime
    cerrada_en: datetime | None = None


class QRResponse(BaseModel):
    session_id: str
    token: str
    ventana_segundos: int


class ScanAttendanceRequest(BaseModel):
    token: str
    huella_dispositivo: str | None = None


class AttendanceRecordOut(BaseModel):
    id: str
    student_id: str
    carnet: str
    nombre: str
    escaneado_en: datetime
    device_id: str | None = None

