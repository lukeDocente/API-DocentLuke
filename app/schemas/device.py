from pydantic import BaseModel


class LinkDeviceRequest(BaseModel):
    huella_dispositivo: str


class DeviceOut(BaseModel):
    id: str
    huella_dispositivo: str
    activo: bool

