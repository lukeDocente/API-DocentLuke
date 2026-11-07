from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_role
from app.models import Assignment, AttendanceRecord, AttendanceSession, Course, Enrollment, Section, Submission, User
from app.schemas.course import CourseCreate, CourseOut, CourseUpdate, SectionCreate, SectionOut, SectionUpdate

router = APIRouter(prefix="/courses", tags=["Cursos"])


@router.get("", response_model=list[CourseOut])
def listar_cursos(
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    query = db.query(Course)
    if current_user.rol == "profesor":
        mis_cursos = query.filter(Course.profesor_id == current_user.id).all()
        # Si el profesor aún no tiene cursos asignados exclusivamente, mostrar los cursos del centro escolar
        cursos = mis_cursos if mis_cursos else db.query(Course).all()
    else:
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

    seccion = Section(course_id=course_id, nombre=req.nombre)
    db.add(seccion)
    db.commit()
    db.refresh(seccion)
    return SectionOut(id=seccion.id, nombre=seccion.nombre)


@router.patch("/{id}", response_model=CourseOut)
def modificar_curso(
    id: str,
    req: CourseUpdate,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    curso = db.query(Course).filter(Course.id == id).first()
    if not curso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "CURSO_NO_ENCONTRADO", "mensaje": "Curso no encontrado"},
        )
    if req.nombre is not None:
        curso.nombre = req.nombre.strip()
    if req.ciclo is not None:
        curso.ciclo = req.ciclo.strip()

    db.commit()
    db.refresh(curso)
    return CourseOut(
        id=curso.id,
        nombre=curso.nombre,
        ciclo=curso.ciclo,
        sections=[SectionOut(id=s.id, nombre=s.nombre) for s in curso.sections],
    )


@router.delete("/{id}", status_code=status.HTTP_200_OK)
def eliminar_curso(
    id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    curso = db.query(Course).filter(Course.id == id).first()
    if not curso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "CURSO_NO_ENCONTRADO", "mensaje": "Curso no encontrado"},
        )

    # Eliminar en cascada dependencias de secciones
    for sec in curso.sections:
        # Sesiones de asistencia y registros
        sesiones = db.query(AttendanceSession).filter(AttendanceSession.section_id == sec.id).all()
        for ses in sesiones:
            db.query(AttendanceRecord).filter(AttendanceRecord.session_id == ses.id).delete()
            db.delete(ses)
        # Matrículas
        db.query(Enrollment).filter(Enrollment.section_id == sec.id).delete()
        db.delete(sec)

    # Eliminar tareas y entregas
    tareas = db.query(Assignment).filter(Assignment.course_id == curso.id).all()
    for t in tareas:
        db.query(Submission).filter(Submission.assignment_id == t.id).delete()
        db.delete(t)

    db.delete(curso)
    db.commit()
    return {"status": "success", "mensaje": f"Curso '{curso.nombre}' eliminado exitosamente"}


@router.patch("/sections/{section_id}", response_model=SectionOut)
def modificar_seccion(
    section_id: str,
    req: SectionUpdate,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    seccion = db.query(Section).filter(Section.id == section_id).first()
    if not seccion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SECCION_NO_ENCONTRADA", "mensaje": "Sección no encontrada"},
        )
    if req.nombre is not None:
        seccion.nombre = req.nombre.strip()

    db.commit()
    db.refresh(seccion)
    return SectionOut(id=seccion.id, nombre=seccion.nombre)


@router.delete("/sections/{section_id}", status_code=status.HTTP_200_OK)
def eliminar_seccion(
    section_id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    seccion = db.query(Section).filter(Section.id == section_id).first()
    if not seccion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "SECCION_NO_ENCONTRADA", "mensaje": "Sección no encontrada"},
        )

    # Limpiar sesiones de asistencia y registros
    sesiones = db.query(AttendanceSession).filter(AttendanceSession.section_id == seccion.id).all()
    for ses in sesiones:
        db.query(AttendanceRecord).filter(AttendanceRecord.session_id == ses.id).delete()
        db.delete(ses)

    db.query(Enrollment).filter(Enrollment.section_id == seccion.id).delete()
    db.delete(seccion)
    db.commit()
    return {"status": "success", "mensaje": f"Sección '{seccion.nombre}' eliminada exitosamente"}


