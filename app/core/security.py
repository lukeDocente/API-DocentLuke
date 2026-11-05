"""Seguridad, criptografía, hashing de contraseñas y tokens firmados.

1. QR de asistencia dinámico: "<sesion_id>.<ventana>.<firma>"
   - ventana = floor(tiempo / QR_WINDOW_SECONDS)
   - ventana actual o anterior (20 segundos con tolerancia)
2. Carnet de alumno: "<student_id>.<firma>"
3. Autenticación con JWT (Argon2 para contraseñas)
4. Dependencias de FastAPI para roles (profesor, alumno, admin)
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import time
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db

ph = PasswordHasher()
security_bearer = HTTPBearer(auto_error=False)


# --- HASHING DE CONTRASEÑAS CON ARGON2 ---
def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        return False


# --- TOKENS JWT ---
ALGORITHM = "HS256"


def crear_access_token(sub: str, rol: str, expires_delta: timedelta | None = None) -> str:
    ahora = datetime.now(timezone.utc)
    exp = ahora + (expires_delta or timedelta(minutes=settings.access_token_minutes))
    payload = {
        "sub": sub,
        "rol": rol,
        "type": "access",
        "iat": ahora,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def crear_refresh_token(sub: str, rol: str) -> str:
    ahora = datetime.now(timezone.utc)
    exp = ahora + timedelta(days=settings.refresh_token_days)
    payload = {
        "sub": sub,
        "rol": rol,
        "type": "refresh",
        "iat": ahora,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decodificar_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "TOKEN_INVALIDO", "mensaje": "Token inválido o expirado"},
            headers={"WWW-Authenticate": "Bearer"},
        )


# --- TOKENS QR FIRMADOS CON HMAC-SHA256 ---
def _firma(secret: str, mensaje: str) -> str:
    return hmac.new(secret.encode(), mensaje.encode(), hashlib.sha256).hexdigest()[:32]


def _ventana(ahora: float | None = None) -> int:
    return int((time.time() if ahora is None else ahora) // settings.qr_window_seconds)


def crear_token_asistencia(sesion_id: str, ahora: float | None = None) -> str:
    ventana = _ventana(ahora)
    return f"{sesion_id}.{ventana}.{_firma(settings.qr_secret, f'{sesion_id}.{ventana}')}"


def validar_token_asistencia(token: str, ahora: float | None = None) -> str | None:
    """Devuelve el sesion_id si el token es válido; None si no."""
    try:
        sesion_id, ventana_txt, firma = token.rsplit(".", 2)
        ventana = int(ventana_txt)
    except ValueError:
        return None
    esperada = _firma(settings.qr_secret, f"{sesion_id}.{ventana}")
    if not hmac.compare_digest(firma, esperada):
        return None
    actual = _ventana(ahora)
    if ventana not in (actual, actual - 1):
        return None
    return sesion_id


def crear_token_carnet(student_id: str) -> str:
    return f"{student_id}.{_firma(settings.qr_secret, 'carnet.' + student_id)}"


def validar_token_carnet(token: str) -> str | None:
    """Devuelve el student_id si la firma es válida; None si no."""
    try:
        student_id, firma = token.rsplit(".", 1)
    except ValueError:
        return None
    esperada = _firma(settings.qr_secret, "carnet." + student_id)
    return student_id if hmac.compare_digest(firma, esperada) else None


# --- DEPENDENCIAS DE USUARIO Y ROL ---
def get_current_user(
    auth: Annotated[HTTPAuthorizationCredentials | None, Depends(security_bearer)],
    db: Annotated[Session, Depends(get_db)],
):
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "NO_AUTENTICADO", "mensaje": "Se requiere token de autenticación"},
        )
    payload = decodificar_token(auth.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "TIPO_TOKEN_INVALIDO", "mensaje": "Se requiere token de acceso"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "PAYLOAD_INVALIDO", "mensaje": "Identificador de usuario faltante"},
        )

    from app.models import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"codigo": "USUARIO_INACTIVO", "mensaje": "Usuario inactivo o no encontrado"},
        )
    return user


def require_role(roles_permitidos: list[str]):
    def role_checker(current_user=Depends(get_current_user)):
        if current_user.rol not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"codigo": "ACCESO_DENEGADO", "mensaje": f"Se requiere uno de los roles: {roles_permitidos}"},
            )
        return current_user
    return role_checker
