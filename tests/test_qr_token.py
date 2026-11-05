from app.core import security
from app.core.config import settings

W = settings.qr_window_seconds


def test_token_asistencia_valido_en_su_ventana():
    t = security.crear_token_asistencia("sesion-1", ahora=1000.0)
    assert security.validar_token_asistencia(t, ahora=1000.0) == "sesion-1"


def test_token_asistencia_acepta_ventana_anterior():
    t = security.crear_token_asistencia("sesion-1", ahora=1000.0)
    assert security.validar_token_asistencia(t, ahora=1000.0 + W) == "sesion-1"


def test_token_asistencia_vence_despues_de_dos_ventanas():
    t = security.crear_token_asistencia("sesion-1", ahora=1000.0)
    assert security.validar_token_asistencia(t, ahora=1000.0 + 2 * W) is None


def test_token_asistencia_alterado_se_rechaza():
    t = security.crear_token_asistencia("sesion-1", ahora=1000.0)
    assert security.validar_token_asistencia(t.replace("sesion-1", "sesion-2"), ahora=1000.0) is None


def test_carnet_firmado_y_alterado():
    t = security.crear_token_carnet("alumno-42")
    assert security.validar_token_carnet(t) == "alumno-42"
    assert security.validar_token_carnet(t.replace("alumno-42", "alumno-43")) is None
