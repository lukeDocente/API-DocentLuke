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


class CourseUpdate(BaseModel):
    nombre: str | None = None
    ciclo: str | None = None


class SectionCreate(BaseModel):
    nombre: str


class SectionUpdate(BaseModel):
    nombre: str | None = None


