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
    if current_user.rol == "profesor" and curso.profesor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "NO_AUTORIZADO", "mensaje": "No tienes permiso en este curso"},
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
    if current_user.rol == "profesor" and tarea.course.profesor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "NO_AUTORIZADO", "mensaje": "No tienes permiso para editar esta tarea"},
        )

    if req.abierta is not None:
        tarea.abierta = req.abierta
    if req.nombre is not None:
        tarea.nombre = req.nombre

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
        # 1. Validar firma del carnet
        student_id = security.validar_token_carnet(item.token_carnet)
        hora_entrega = item.entregada_en or ahora_servidor

        if not student_id:
            resultados.append(
                BatchSubmissionResult(
                    token_carnet=item.token_carnet,
                    entregada_en=hora_entrega,
                    recibida_en=ahora_servidor,
                    estado="invalido",
                    mensaje="Carnet con firma inválida o alterada",
                )
            )
            continue

        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            resultados.append(
                BatchSubmissionResult(
                    token_carnet=item.token_carnet,
                    student_id=student_id,
                    entregada_en=hora_entrega,
                    recibida_en=ahora_servidor,
                    estado="invalido",
                    mensaje="Estudiante no encontrado en el sistema",
                )
            )
            continue

        # 2. Verificar inscripción en alguna sección del curso
        enrollment = db.query(Enrollment).join(Section).filter(
            Enrollment.student_id == student.id,
            Section.course_id == tarea.course_id,
        ).first()

        seccion_nombre = enrollment.section.nombre if enrollment else "N/A"
        materia_nombre = tarea.course.nombre

        if not enrollment:
            resultados.append(
                BatchSubmissionResult(
                    token_carnet=item.token_carnet,
                    student_id=student.id,
                    carnet=student.carnet,
                    nombre=student.nombre,
                    seccion=seccion_nombre,
                    materia=materia_nombre,
                    entregada_en=hora_entrega,
                    recibida_en=ahora_servidor,
                    estado="no_inscrito",
                    mensaje="El estudiante no está inscrito en este curso",
                )
            )
            continue

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

