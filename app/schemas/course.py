from datetime import datetime
from pydantic import BaseModel


class SectionOut(BaseModel):
    id: str
    nombre: str


class CourseOut(BaseModel):
    id: str
    nombre: str
    ciclo: str
    sections: list[SectionOut] = []


class CourseCreate(BaseModel):
    nombre: str
    ciclo: str


class SectionCreate(BaseModel):
    nombre: str

