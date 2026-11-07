"""Generador de carnets estudiantiles en imagen PNG de alta definición.
Diseñado con formato estándar de carnet institucional con QR de alta legibilidad.
"""
import io
import os
from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.core import security


def _obtener_fuente(size: int, bold: bool = False):
    """Carga una fuente TrueType del sistema si está disponible, o la predeterminada de PIL."""
    fuentes_posibles = [
        "arialbd.ttf" if bold else "arial.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "calibrib.ttf" if bold else "calibri.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for f in fuentes_posibles:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generar_carnet_png(
    student_id: str,
    carnet: str,
    nombre: str,
    institucion: str = 'CENTRO ESCOLAR "JOSE QUETGLAS"',
    seccion: str = "5° Grado - Sección A",
    ano_lectivo: str = "2026",
) -> bytes:
    """Genera una imagen PNG del carnet estudiantil con diseño institucional y código QR firmado."""
    # Dimensiones estándar del carnet: 900 x 540 px (aspect ratio 5:3)
    width = 900
    height = 540
    img = Image.new("RGB", (width, height), color=(248, 250, 252))  # Fondo gris pizarra muy suave (#F8FAFC)
    draw = ImageDraw.Draw(img)

    # 1. Borde exterior redondeado y sombra
    draw.rectangle([(0, 0), (width, height)], fill=(255, 255, 255))
    draw.rectangle([(0, 0), (width, 10)], fill=(14, 116, 144))  # Franja superior celeste/teal

    # 2. Encabezado institucional azul profundo
    draw.rectangle([(0, 10), (width, 115)], fill=(30, 58, 138))  # Azul Marino (#1E3A8A)

    font_institucion = _obtener_fuente(24, bold=True)
    font_subtitulo = _obtener_fuente(15, bold=False)
    font_badge = _obtener_fuente(13, bold=True)

    # Texto de institución centrado en el banner
    draw.text((30, 26), institucion.upper(), fill=(255, 255, 255), font=font_institucion)
    draw.text((30, 62), f"MATRÍCULA OFICIAL • AÑO LECTIVO {ano_lectivo} • EL SALVADOR", fill=(203, 213, 225), font=font_subtitulo)
    draw.text((30, 84), "SISTEMA INTEGRADO DE ASISTENCIA Y CONTROL ACADÉMICO", fill=(147, 197, 253), font=font_subtitulo)

    # 3. Badge "CARNET DEL ESTUDIANTE"
    badge_x = width - 230
    draw.rounded_rectangle([(badge_x, 38), (width - 30, 78)], radius=8, fill=(234, 179, 8))  # Amarillo dorado
    draw.text((badge_x + 18, 48), "CARNET OFICIAL", fill=(15, 23, 42), font=font_badge)

    # 4. Avatar simbólico o silueta de estudiante
    avatar_box = [(40, 150), (190, 310)]
    draw.rounded_rectangle(avatar_box, radius=12, fill=(241, 245, 249), outline=(203, 213, 225), width=2)
    # Dibujar cabeza y hombros estilizados
    draw.ellipse([(90, 175), (140, 225)], fill=(148, 163, 184))
    draw.pieslice([(65, 235), (165, 335)], 180, 360, fill=(148, 163, 184))

    # 5. Información del Estudiante
    info_x = 220
    font_label = _obtener_fuente(14, bold=True)
    font_nombre = _obtener_fuente(22, bold=True)
    font_nie = _obtener_fuente(26, bold=True)
    font_seccion = _obtener_fuente(18, bold=False)

    # Nombre del alumno (si es muy largo se puede partir en dos líneas)
    draw.text((info_x, 145), "ESTUDIANTE:", fill=(100, 116, 139), font=font_label)
    
    # Manejar nombres largos en 2 líneas si superan 30 caracteres
    partes_nombre = nombre.strip().split(",")
    if len(partes_nombre) == 2:
        apellidos = partes_nombre[0].strip()
        nombres = partes_nombre[1].strip()
        draw.text((info_x, 168), apellidos, fill=(15, 23, 42), font=font_nombre)
        draw.text((info_x, 196), nombres, fill=(30, 41, 59), font=font_nombre)
        offset_y = 232
    else:
        draw.text((info_x, 168), nombre[:32], fill=(15, 23, 42), font=font_nombre)
        offset_y = 205

    # Badge de NIE / Carnet
    draw.text((info_x, offset_y), "NÚMERO DE IDENTIFICACIÓN ESTUDIANTIL (NIE):", fill=(100, 116, 139), font=font_label)
    draw.rounded_rectangle([(info_x, offset_y + 22), (info_x + 230, offset_y + 70)], radius=8, fill=(238, 242, 255), outline=(99, 102, 241), width=2)
    draw.text((info_x + 16, offset_y + 28), f"NIE: {carnet}", fill=(49, 46, 129), font=font_nie)

    # Grado y Sección
    draw.text((info_x, offset_y + 85), "GRADO Y SECCIÓN:", fill=(100, 116, 139), font=font_label)
    draw.text((info_x, offset_y + 107), seccion, fill=(15, 23, 42), font=font_seccion)

    # 6. Generar Código QR de Alta Resolución
    # El QR contiene el token firmado HMAC del carnet
    token_qr = security.crear_token_carnet(student_id)
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(token_qr)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0F172A", back_color="white").convert("RGB")

    # Redimensionar QR a 220x220 px
    qr_size = 220
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)

    # Pegar QR en el carnet
    qr_x = width - qr_size - 40
    qr_y = 150
    # Marco para el código QR
    draw.rounded_rectangle([(qr_x - 10, qr_y - 10), (qr_x + qr_size + 10, qr_y + qr_size + 10)], radius=12, fill=(255, 255, 255), outline=(226, 232, 240), width=2)
    img.paste(qr_img, (qr_x, qr_y))

    # Texto debajo del QR
    font_qr_desc = _obtener_fuente(12, bold=True)
    draw.text((qr_x + 10, qr_y + qr_size + 16), "ESCANEO ASISTENCIA Y TAREAS", fill=(71, 85, 105), font=font_qr_desc)

    # 7. Barra inferior de validez y seguridad
    draw.rectangle([(0, height - 42), (width, height)], fill=(241, 245, 249))
    draw.line([(0, height - 42), (width, height - 42)], fill=(226, 232, 240), width=1)
    font_footer = _obtener_fuente(12, bold=False)
    draw.text((40, height - 30), "DOCUMENTO OFICIAL DEL ESTUDIANTE • VÁLIDO PARA PASE DE LISTA Y RECEPCIÓN DE TRABAJOS ACADÉMICOS", fill=(100, 116, 139), font=font_footer)

    # Exportar a bytes en formato PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(300, 300), optimize=True)
    return buf.getvalue()
