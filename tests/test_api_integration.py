import pytest
from app.core.db import SessionLocal, init_db
from app.seed import seed
from app.models import Assignment, Course, Section, Student, User
from app.schemas.auth import LoginRequest
from app.schemas.attendance import SessionCreate, ScanAttendanceRequest
from app.schemas.assignment import AssignmentCreate, BatchSubmissionsRequest, BatchSubmissionItem, SubmissionGradeRequest
from app.schemas.device import LinkDeviceRequest
from app.routers import auth, courses, attendance, assignments, submissions, student, verify


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()
    seed()


def test_login_profesor_y_alumno():
    db = SessionLocal()
    try:
        # Profesor
        res_prof = auth.login(LoginRequest(email="profesor@luke.edu", password="Profesor123*"), db)
        assert res_prof.rol == "profesor"
        assert res_prof.email == "profesor@luke.edu"
        assert len(res_prof.access_token) > 0

        # Alumno
        res_alu = auth.login(LoginRequest(email="alumno@luke.edu", password="Alumno123*"), db)
        assert res_alu.rol == "alumno"
        assert res_alu.carnet == "2026-ALU-001"
        assert res_alu.nombre == "Carlos Mendoza"
    finally:
        db.close()


def test_flujo_asistencia_completo():
    db = SessionLocal()
    try:
        profesor = db.query(User).filter(User.email == "profesor@luke.edu").first()
        alumno = db.query(User).filter(User.email == "alumno@luke.edu").first()

        # 1. Profesor consulta sus cursos
        cursos = courses.listar_cursos(current_user=profesor, db=db)
        assert len(cursos) > 0
        seccion_id = cursos[0].sections[0].id

        # 2. Profesor abre sesión de asistencia
        sesion = attendance.abrir_sesion(SessionCreate(section_id=seccion_id), current_user=profesor, db=db)
        assert sesion.id is not None
        assert sesion.cerrada_en is None

        # 3. Profesor solicita token QR dinámico
        qr_info = attendance.obtener_qr_sesion(id=sesion.id, current_user=profesor, db=db)
        assert qr_info.session_id == sesion.id
        assert len(qr_info.token) > 0

        # 4. Alumno vincula su teléfono
        device = student.vincular_dispositivo(LinkDeviceRequest(huella_dispositivo="phone-device-xyz"), current_user=alumno, db=db)
        assert device.activo is True

        # 5. Alumno escanea el QR dinámico
        scan_res = attendance.registrar_asistencia(
            ScanAttendanceRequest(token=qr_info.token, huella_dispositivo="phone-device-xyz"),
            current_user=alumno,
            db=db,
        )
        assert scan_res["estado"] == "confirmado"
        assert scan_res["carnet"] == "2026-ALU-001"

        # 6. Escaneo duplicado del mismo alumno
        dup_res = attendance.registrar_asistencia(
            ScanAttendanceRequest(token=qr_info.token, huella_dispositivo="phone-device-xyz"),
            current_user=alumno,
            db=db,
        )
        assert dup_res["estado"] == "ya_registrada"

        # 7. Profesor ve la lista de asistentes en vivo
        records = attendance.listar_asistentes_sesion(id=sesion.id, current_user=profesor, db=db)
        assert len(records) >= 1
        assert any(r.carnet == "2026-ALU-001" for r in records)

        # 8. Profesor cierra la sesión
        cerrada = attendance.cerrar_sesion(id=sesion.id, current_user=profesor, db=db)
        assert cerrada.cerrada_en is not None
    finally:
        db.close()


def test_flujo_tareas_lote_calificacion_y_verificacion():
    db = SessionLocal()
    try:
        profesor = db.query(User).filter(User.email == "profesor@luke.edu").first()
        alumno = db.query(User).filter(User.email == "alumno@luke.edu").first()

        # 1. Alumno obtiene su carnet con QR firmado
        carnet_info = student.obtener_carnet(current_user=alumno, db=db)
        assert carnet_info.carnet == "2026-ALU-001"
        carnet_token = carnet_info.carnet_qr_token

        # 2. Profesor crea una tarea
        curso = db.query(Course).filter(Course.profesor_id == profesor.id).first()
        nueva_tarea = assignments.crear_tarea(
            AssignmentCreate(course_id=curso.id, nombre="Examen Corto 1", puntaje_max=10.0),
            current_user=profesor,
            db=db,
        )
        assert nueva_tarea.id is not None
        tarea_id = nueva_tarea.id

        # 3. Profesor escanea lote de entregas
        batch_res = assignments.procesar_lote_entregas(
            id=tarea_id,
            req=BatchSubmissionsRequest(items=[BatchSubmissionItem(token_carnet=carnet_token)]),
            current_user=profesor,
            db=db,
        )
        assert batch_res.total == 1
        item_proc = batch_res.procesados[0]
        assert item_proc.estado == "aceptado"
        assert item_proc.carnet == "2026-ALU-001"
        submission_id = item_proc.submission_id
        folio = item_proc.folio

        # 4. Segundo escaneo del mismo carnet detecta duplicado
        batch_dup = assignments.procesar_lote_entregas(
            id=tarea_id,
            req=BatchSubmissionsRequest(items=[BatchSubmissionItem(token_carnet=carnet_token)]),
            current_user=profesor,
            db=db,
        )
        assert batch_dup.procesados[0].estado == "duplicado"

        # 5. Profesor califica la entrega con 9.5
        graded = submissions.calificar_entrega(
            id=submission_id,
            req=SubmissionGradeRequest(nota=9.5),
            current_user=profesor,
            db=db,
        )
        assert graded.nota == 9.5

        # 6. Verificación pública del folio (sin login)
        verif = verify.verificar_constancia(folio=folio, db=db)
        assert verif.valido is True
        assert verif.alumno == "Carlos Mendoza"
        assert verif.nota == 9.5
        assert verif.tarea == "Examen Corto 1"
    finally:
        db.close()
