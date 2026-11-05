import os
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
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        # Si contiene placeholders aún no reemplazados, usar SQLite local
        if "[region]" in url or "[TU_" in url or "[YOUR" in url:
            return "sqlite:///./asistencia.db"

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
        return url


settings = Settings()
