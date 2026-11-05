import os
import re
from urllib.parse import quote_plus
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        extra="ignore",
    )

    database_url: str = "sqlite:///./asistencia.db"
    jwt_secret: str = "LukeDocente_IA_JWT_SECRET_2026"
    qr_secret: str = "LukeDocente_IA"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    qr_window_seconds: int = 20
    supabase_url: str | None = None
    supabase_key: str | None = None

    @property
    def sqlalchemy_database_url(self) -> str:
        url = (self.database_url or "").strip()

        # Si está vacío o tiene placeholders de ejemplo, usar SQLite
        if not url or "[region]" in url or "[TU_" in url or "[YOUR" in url:
            return "sqlite:///./asistencia.db"

        # Limpiar corchetes y comillas accidentales en contraseñas como ["mi_password"]
        url = re.sub(r':\["([^"]+)"\]@', r':\1@', url)
        url = re.sub(r':\[([^\]]+)\]@', r':\1@', url)
        url = re.sub(r':"([^"]+)"@', r':\1@', url)

        # Si la contraseña contiene '#' sin codificar como '%23', codificarla
        # formato: postgresql://user:password@host
        match = re.search(r'://([^:]+):([^@]+)@', url)
        if match:
            user = match.group(1)
            raw_pass = match.group(2)
            if "#" in raw_pass and not "%23" in raw_pass:
                encoded_pass = raw_pass.replace("#", "%23")
                url = url.replace(f":{raw_pass}@", f":{encoded_pass}@", 1)

        # Normalizar prefijo postgres
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        # Adaptar driver psycopg3 vs psycopg2 según el entorno
        if "postgresql+psycopg://" in url:
            try:
                import psycopg  # noqa: F401
            except ImportError:
                url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            try:
                import psycopg  # noqa: F401
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            except ImportError:
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

        # Para Supabase remoto, asegurar sslmode=require si no está presente
        if ("supabase.co" in url or "pooler.supabase.com" in url) and "sslmode" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sslmode=require"

        return url


settings = Settings()
