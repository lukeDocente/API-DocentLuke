from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.db import get_db
from app.core.security import require_role
from app.models import (
    Assignment,
    Course,
    Enrollment,
    GradeAudit,
    Section,
    Student,
    Submission,
    User,
)
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    BatchSubmissionsRequest,
    BatchSubmissionsResponse,
    BatchSubmissionResult,
    SubmissionGradeRequest,
    SubmissionOut,
)

router = APIRouter(prefix="/assignments", tags=["Tareas y Entregas"])


@router.get("", response_model=list[AssignmentOut])
def listar_tareas(
    course_id: str | None = None,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    """Lista todas las tareas creadas, opcionalmente filtradas por curso."""
    query = db.query(Assignment)
    if course_id:
        query = query.filter(Assignment.course_id == course_id)
    tareas = query.order_by(Assignment.created_at.desc()).all()
    return [
        AssignmentOut(
            id=t.id,
            course_id=t.course_id,
            nombre=t.nombre,
            puntaje_max=float(t.puntaje_max),
            abierta=t.abierta,
            created_at=t.created_at,
        )
        for t in tareas
    ]


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def crear_tarea(
    req: AssignmentCreate,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    curso = db.query(Course).filter(Course.id == req.course_id).first()
    if not curso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "CURSO_NO_ENCONTRADO", "mensaje": "Curso no encontrado"},
        )

    tarea = Assignment(
        course_id=req.course_id,
        nombre=req.nombre,
        puntaje_max=req.puntaje_max,
        abierta=True,
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)

    return AssignmentOut(
        id=tarea.id,
        course_id=tarea.course_id,
        nombre=tarea.nombre,
        puntaje_max=float(tarea.puntaje_max),
        abierta=tarea.abierta,
        created_at=tarea.created_at,
    )


@router.patch("/{id}", response_model=AssignmentOut)
def actualizar_tarea(
    id: str,
    req: AssignmentUpdate,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    tarea = db.query(Assignment).filter(Assignment.id == id).first()
    if not tarea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "TAREA_NO_ENCONTRADA", "mensaje": "Tarea no encontrada"},
        )

    if req.abierta is not None:
        tarea.abierta = req.abierta
    if req.nombre is not None:
        tarea.nombre = req.nombre.strip()
    if req.puntaje_max is not None:
        tarea.puntaje_max = req.puntaje_max

    db.commit()
    db.refresh(tarea)

    return AssignmentOut(
        id=tarea.id,
        course_id=tarea.course_id,
        nombre=tarea.nombre,
        puntaje_max=float(tarea.puntaje_max),
        abierta=tarea.abierta,
        created_at=tarea.created_at,
    )


@router.delete("/{id}", status_code=status.HTTP_200_OK)
def eliminar_tarea(
    id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    tarea = db.query(Assignment).filter(Assignment.id == id).first()
    if not tarea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "TAREA_NO_ENCONTRADA", "mensaje": "Tarea no encontrada"},
        )

    # Eliminar entregas y auditorías asociadas
    submissions = db.query(Submission).filter(Submission.assignment_id == tarea.id).all()
    for s in submissions:
        db.query(GradeAudit).filter(GradeAudit.submission_id == s.id).delete()
        db.delete(s)

    db.delete(tarea)
    db.commit()
    return {"status": "success", "mensaje": f"Tarea '{tarea.nombre}' eliminada exitosamente"}


@router.get("/{id}/submissions", response_model=list[SubmissionOut])
def listar_entregas_tarea(
    id: str,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    tarea = db.query(Assignment).filter(Assignment.id == id).first()
    if not tarea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "TAREA_NO_ENCONTRADA", "mensaje": "Tarea no encontrada"},
        )

    submissions = db.query(Submission).filter(Submission.assignment_id == id).order_by(Submission.entregada_en.desc()).all()

    resultados = []
    for s in submissions:
        # Obtener sección si está matriculado
        enrollment = db.query(Enrollment).join(Section).filter(
            Enrollment.student_id == s.student_id,
            Section.course_id == tarea.course_id,
        ).first()
        seccion_nombre = enrollment.section.nombre if enrollment else "N/A"

        resultados.append(
            SubmissionOut(
                id=s.id,
                assignment_id=s.assignment_id,
                student_id=s.student_id,
                carnet=s.student.carnet,
                nombre=s.student.nombre,
                seccion=seccion_nombre,
                materia=tarea.course.nombre,
                entregada_en=s.entregada_en,
                recibida_en=s.recibida_en,
                nota=float(s.nota) if s.nota is not None else None,
                folio=s.folio,
            )
        )
    return resultados


@router.post("/{id}/submissions/batch", response_model=BatchSubmissionsResponse)
def procesar_lote_entregas(
    id: str,
    req: BatchSubmissionsRequest,
    current_user: User = Depends(require_role(["profesor", "admin"])),
    db: Session = Depends(get_db),
):
    tarea = db.query(Assignment).filter(Assignment.id == id).first()
    if not tarea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "TAREA_NO_ENCONTRADA", "mensaje": "Tarea no encontrada"},
        )
    if not tarea.abierta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "TAREA_CERRADA", "mensaje": "La tarea está cerrada para recibir entregas"},
        )

    ahora_servidor = datetime.now(timezone.utc)
    resultados: list[BatchSubmissionResult] = []

    for item in req.items:
        token = item.token_carnet.strip()
        hora_entrega = item.entregada_en or ahora_servidor

        # 1. Validar firma del carnet o buscar directamente por NIE o ID
        student_id = security.validar_token_carnet(token)
        student = None
        if student_id:
            student = db.query(Student).filter(Student.id == student_id).first()

        if not student:
            student = db.query(Student).filter((Student.carnet == token) | (Student.id == token)).first()

        if not student:
            resultados.append(
                BatchSubmissionResult(
                    token_carnet=item.token_carnet,
                    entregada_en=hora_entrega,
                    recibida_en=ahora_servidor,
                    estado="invalido",
                    mensaje="Carnet o código de estudiante no encontrado",
                )
            )
            continue

        # 2. Verificar inscripción en alguna sección del curso (o auto-inscribir)
        enrollment = db.query(Enrollment).join(Section).filter(
            Enrollment.student_id == student.id,
            Section.course_id == tarea.course_id,
        ).first()

        if not enrollment:
            seccion_primera = db.query(Section).filter(Section.course_id == tarea.course_id).first()
            if seccion_primera:
                enrollment = Enrollment(student_id=student.id, section_id=seccion_primera.id)
                db.add(enrollment)
                db.commit()
                db.refresh(enrollment)

        seccion_nombre = enrollment.section.nombre if enrollment else "Sección A"
        materia_nombre = tarea.course.nombre

        # 3. Comprobar si ya entregó
        existente = db.query(Submission).filter(
            Submission.assignment_id == tarea.id,
            Submission.student_id == student.id,
        ).first()

        if existente:
            resultados.append(
                BatchSubmissionResult(
                    token_carnet=item.token_carnet,
                    student_id=student.id,
                    carnet=student.carnet,
                    nombre=student.nombre,
                    seccion=seccion_nombre,
                    materia=materia_nombre,
                    entregada_en=existente.entregada_en,
                    recibida_en=existente.recibida_en,
                    estado="duplicado",
                    mensaje=f"Ya entregó previamente el {existente.entregada_en.strftime('%d/%m/%Y a las %H:%M')}",
                    submission_id=existente.id,
                    folio=existente.folio,
                    nota=float(existente.nota) if existente.nota is not None else None,
                )
            )
            continue

        # 4. Crear nueva entrega
        nueva_entrega = Submission(
            assignment_id=tarea.id,
            student_id=student.id,
            entregada_en=hora_entrega,
            recibida_en=ahora_servidor,
            folio=str(uuid.uuid4()),
        )
        db.add(nueva_entrega)
        db.commit()
        db.refresh(nueva_entrega)

        resultados.append(
            BatchSubmissionResult(
                token_carnet=item.token_carnet,
                student_id=student.id,
                carnet=student.carnet,
                nombre=student.nombre,
                seccion=seccion_nombre,
                materia=materia_nombre,
                entregada_en=nueva_entrega.entregada_en,
                recibida_en=nueva_entrega.recibida_en,
                estado="aceptado",
                mensaje="Entrega registrada exitosamente",
                submission_id=nueva_entrega.id,
                folio=nueva_entrega.folio,
                nota=None,
            )
        )

    return BatchSubmissionsResponse(
        assignment_id=tarea.id,
        total=len(resultados),
        procesados=resultados,
    )

