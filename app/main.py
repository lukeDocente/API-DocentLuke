from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import init_db
from app.routers import admin, assignments, attendance, auth, courses, student, submissions, sync, verify


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar tablas al arrancar la aplicación
    init_db()
    yield


app = FastAPI(
    title="Asistencia y Tareas con QR",
    description="API REST para control de asistencia con QR dinámico y registro/calificación de tareas.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS habilitado para Flutter (emulador, web, local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"estado": "ok"}


# Registro de routers bajo /api/v1
app.include_router(auth.router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")
app.include_router(assignments.router, prefix="/api/v1")
app.include_router(submissions.router, prefix="/api/v1")
app.include_router(student.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

# Ruta de verificación pública bajo /api/v1 y /verify directo según SDD
app.include_router(verify.router, prefix="/api/v1")
app.include_router(verify.router)
