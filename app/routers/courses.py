from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_role
from app.models import Course, Section, User
from app.schemas.course import CourseCreate, CourseOut, SectionCreate, SectionOut

router = APIRouter(prefix="/courses", tags=["Cursos"])


@router.get("", response_model=list[CourseOut])
def listar_cursos(
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    query = db.query(Course)
    if current_user.rol == "profesor":
        query = query.filter(Course.profesor_id == current_user.id)
    cursos = query.all()

    return [
        CourseOut(
            id=c.id,
            nombre=c.nombre,
            ciclo=c.ciclo,
            sections=[SectionOut(id=s.id, nombre=s.nombre) for s in c.sections],
        )
        for c in cursos
    ]


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def crear_curso(
    req: CourseCreate,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    curso = Course(
        nombre=req.nombre,
        profesor_id=current_user.id,
        ciclo=req.ciclo,
    )
    db.add(curso)
    db.commit()
    db.refresh(curso)
    return CourseOut(id=curso.id, nombre=curso.nombre, ciclo=curso.ciclo, sections=[])


@router.post("/{course_id}/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def crear_seccion(
    course_id: str,
    req: SectionCreate,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    curso = db.query(Course).filter(Course.id == course_id).first()
    if not curso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "CURSO_NO_ENCONTRADO", "mensaje": "Curso no encontrado"},
        )
    if current_user.rol == "profesor" and curso.profesor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "NO_AUTORIZADO", "mensaje": "No tienes acceso a este curso"},
        )

    seccion = Section(course_id=course_id, nombre=req.nombre)
    db.add(seccion)
    db.commit()
    db.refresh(seccion)
    return SectionOut(id=seccion.id, nombre=seccion.nombre)

