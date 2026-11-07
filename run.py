import os
import sys
import uvicorn

if __name__ == "__main__":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    port = int(os.environ.get("PORT", 8000))
    print(f"==> Iniciando Asistencia QR API en el puerto {port}...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info", loop="asyncio")

