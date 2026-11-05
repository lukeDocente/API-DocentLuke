# Backend (FastAPI)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # y cambia los secretos
uvicorn app.main:app --reload                         # http://localhost:8000/docs
pytest                                                # prueba del token QR
```

Siguiente paso (fase 1): `alembic init alembic`, migración inicial con los modelos de `app/models`,
y routers `auth` y `admin` según la sección «Diseño de API» del SDD (`docs/SDD.md`).
