"""Modelos SQLAlchemy 2.0 según el SDD de Asistencia y Tareas con QR.

Tablas:
- users: Profesores, alumnos y administradores.
- students: Perfil de alumnos asociado 1:1 a users.
- courses: Materias asignadas a profesores.
- sections: Secciones de cada materia.
- enrollments: Asignación de alumnos a secciones.
- attendance_sessions: Sesiones de asistencia creadas por profesores.
- attendance_records: Registros de asistencia únicos por (sesión, alumno).
- assignments: Tareas por curso con puntaje máximo.
- submissions: Entregas de tarea con fecha, folio único y nota de 0 a 10.
- devices: Dispositivos vinculados a cuentas de alumno.
- deliveries_log: Bitácora de constancias enviadas o generadas.
- grade_audit: Bitácora de auditoría para cambios de notas.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora, onupdate=_ahora)


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20))  # profesor | alumno | admin
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    student: Mapped["Student | None"] = relationship("Student", back_populates="user", uselist=False)
    devices: Mapped[list["Device"]] = relationship("Device", back_populates="user")
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="profesor")


class Student(Base):
    __tablename__ = "students"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    carnet: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(255))
    tel_encargado: Mapped[str | None] = mapped_column(String(30), nullable=True)
    consentimiento_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="student")
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="student")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="student")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="student")


class Course(Base):
    __tablename__ = "courses"

    nombre: Mapped[str] = mapped_column(String(255))
    profesor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ciclo: Mapped[str] = mapped_column(String(20))

    profesor: Mapped["User"] = relationship("User", back_populates="courses")
    sections: Mapped[list["Section"]] = relationship("Section", back_populates="course", cascade="all, delete-orphan")
    assignments: Mapped[list["Assignment"]] = relationship("Assignment", back_populates="course", cascade="all, delete-orphan")


class Section(Base):
    __tablename__ = "sections"

    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(50))

    course: Mapped["Course"] = relationship("Course", back_populates="sections")
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="section", cascade="all, delete-orphan")
    attendance_sessions: Mapped[list["AttendanceSession"]] = relationship("AttendanceSession", back_populates="section", cascade="all, delete-orphan")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "section_id", name="uq_student_section"),)

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"), index=True)

    student: Mapped["Student"] = relationship("Student", back_populates="enrollments")
    section: Mapped["Section"] = relationship("Section", back_populates="enrollments")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "huella_dispositivo", name="uq_user_device"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    huella_dispositivo: Mapped[str] = mapped_column(String(128), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship("User", back_populates="devices")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="device")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"), index=True)
    abierta_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    secreto_sesion: Mapped[str | None] = mapped_column(String(64), default=_uuid, nullable=True)

    section: Mapped["Section"] = relationship("Section", back_populates="attendance_sessions")
    records: Mapped[list["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_session_student"),)

    session_id: Mapped[str] = mapped_column(ForeignKey("attendance_sessions.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    escaneado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)

    session: Mapped["AttendanceSession"] = relationship("AttendanceSession", back_populates="records")
    student: Mapped["Student"] = relationship("Student", back_populates="attendance_records")
    device: Mapped["Device | None"] = relationship("Device", back_populates="attendance_records")


class Assignment(Base):
    __tablename__ = "assignments"

    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(255))
    puntaje_max: Mapped[float] = mapped_column(Numeric(4, 2), default=10.0)
    abierta: Mapped[bool] = mapped_column(Boolean, default=True)

    course: Mapped["Course"] = relationship("Course", back_populates="assignments")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="assignment", cascade="all, delete-orphan")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_assignment_student"),
        CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 10)", name="ck_nota_0_10"),
    )

    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    entregada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Hora reportada por dispositivo
    recibida_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)  # Hora oficial servidor
    nota: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    folio: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=_uuid)

    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="submissions")
    student: Mapped["Student"] = relationship("Student", back_populates="submissions")
    deliveries: Mapped[list["DeliveryLog"]] = relationship("DeliveryLog", back_populates="submission", cascade="all, delete-orphan")
    audits: Mapped[list["GradeAudit"]] = relationship("GradeAudit", back_populates="submission", cascade="all, delete-orphan")


class DeliveryLog(Base):
    __tablename__ = "deliveries_log"

    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    canal: Mapped[str] = mapped_column(String(20))  # pdf | png | whatsapp
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | enviado | error
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detalles: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission: Mapped["Submission"] = relationship("Submission", back_populates="deliveries")


class GradeAudit(Base):
    __tablename__ = "grade_audit"

    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    usuario_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    nota_anterior: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    nota_nueva: Mapped[float] = mapped_column(Numeric(4, 2))
    cambiado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    submission: Mapped["Submission"] = relationship("Submission", back_populates="audits")
    usuario: Mapped["User"] = relationship("User")
