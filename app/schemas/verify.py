from datetime import datetime
from pydantic import BaseModel


class FolioVerificationOut(BaseModel):
    valido: bool
    folio: str
    alumno: str
    carnet: str
    tarea: str
    materia: str
    profesor: str
    entregada_en: datetime
    nota: float | None = None
    puntaje_max: float


class LinkDeviceRequest(BaseModel):
    huella_dispositivo: str


class DeviceOut(BaseModel):
    id: str
    huella_dispositivo: str
    activo: bool

