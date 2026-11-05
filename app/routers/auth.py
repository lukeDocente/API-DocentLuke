from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core import security
from app.models import User, Student
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not security.verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "CREDENCIALES_INVALIDAS", "mensaje": "Correo o contraseña incorrectos"},
        )
    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "USUARIO_INACTIVO", "mensaje": "La cuenta se encuentra inactiva"},
        )

    access_token = security.crear_access_token(sub=user.id, rol=user.rol)
    refresh_token = security.crear_refresh_token(sub=user.id, rol=user.rol)

    nombre = None
    carnet = None
    if user.rol == "alumno" and user.student:
        nombre = user.student.nombre
        carnet = user.student.carnet

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        email=user.email,
        rol=user.rol,
        nombre=nombre,
        carnet=carnet,
    )


@router.post("/refresh")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    payload = security.decodificar_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "TIPO_TOKEN_INVALIDO", "mensaje": "Se requiere un token de refresco válido"},
        )
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.activo.is_(True)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "USUARIO_NO_ENCONTRADO", "mensaje": "Usuario no encontrado o inactivo"},
        )

    new_access_token = security.crear_access_token(sub=user.id, rol=user.rol)
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }

