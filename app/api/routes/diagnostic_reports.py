# -*- coding: utf-8 -*-
"""Endpoint para recibir reportes de diagnostico del SGC desktop.

Cualquier SGC instalado puede subir un ZIP de reporte de error sin
autenticacion. El backend:
1. Guarda el ZIP en filesystem (rotacion cada 90 dias)
2. Manda email al admin (REPORT_DESTINATION) con el ZIP adjunto

Asi el admin no necesita pedir reportes por WhatsApp cada vez.

Variables de entorno requeridas:
- SMTP_HOST              (ej. smtp.gmail.com)
- SMTP_PORT              (ej. 587)
- SMTP_USER              (cuenta gmail dedicada)
- SMTP_PASSWORD          (App Password, no la pass normal)
- SMTP_FROM              (igual a SMTP_USER usualmente)
- REPORT_DESTINATION     (email destino del admin)
- SMTP_USE_TLS           ('1' o '0', default '1')

Si las variables no estan setadas, el endpoint igual recibe y guarda
el ZIP, pero NO manda email. Logueado como WARNING para debug.
"""

import logging
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostic-reports", tags=["diagnostic-reports"])

# Path donde se guardan los ZIPs recibidos.
# En DO el filesystem es efimero pero sobrevive entre requests del mismo
# proceso. Para persistencia real, eventualmente migrar a Spaces (S3).
_REPORTS_DIR = Path("/tmp/diagnostic_reports")
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Limite de tamano (50 MB) - los reportes tipicos rondan 10-15 MB
_MAX_REPORT_BYTES = 50 * 1024 * 1024


class DiagnosticUploadResponse(BaseModel):
    ok: bool
    report_id: str
    email_sent: bool
    size_bytes: int
    message: str


def _send_report_email(zip_path: Path, comment: str, machine_id: str,
                       hostname: str, app_version: str) -> bool:
    """Manda email con el ZIP adjunto al admin.

    Retorna True si se envio OK, False si fallo (sin levantar excepcion
    para que el endpoint igual responda OK con email_sent=False).
    """
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = os.environ.get("SMTP_PORT", "587").strip()
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()
    smtp_from = os.environ.get("SMTP_FROM", smtp_user).strip()
    dest = os.environ.get("REPORT_DESTINATION", "").strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "1").strip() != "0"

    if not (smtp_host and smtp_user and smtp_pass and dest):
        log.warning(
            "SMTP no configurado completamente "
            f"(host={bool(smtp_host)}, user={bool(smtp_user)}, "
            f"pass={bool(smtp_pass)}, dest={bool(dest)}). "
            "Reporte guardado pero NO enviado por email."
        )
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = f"[ESA625] Reporte de error - {machine_id[:8]} ({app_version})"
        msg["From"] = smtp_from
        msg["To"] = dest

        body = (
            f"Nuevo reporte de error del SGC ESA625:\n\n"
            f"Maquina: {machine_id}\n"
            f"Hostname: {hostname}\n"
            f"Version SGC: {app_version}\n"
            f"Fecha: {datetime.now().isoformat(timespec='seconds')}\n\n"
            f"--- Comentario del tecnico ---\n"
            f"{comment or '(sin comentario)'}\n\n"
            f"--- Adjunto ---\n"
            f"{zip_path.name} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)\n\n"
            f"Para descifrar los logs: tools/decrypt_diagnostic.py\n"
        )
        msg.set_content(body)

        # Adjuntar ZIP
        with open(zip_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="zip",
                filename=zip_path.name,
            )

        port = int(smtp_port)
        if use_tls:
            with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        log.info(f"Email enviado a {dest} con reporte {zip_path.name}")
        return True

    except Exception as e:
        log.exception(f"Error enviando email: {e}")
        return False


def _cleanup_old_reports(max_age_days: int = 90) -> int:
    """Borra reportes mas viejos que max_age_days. Retorna cantidad borrada."""
    if not _REPORTS_DIR.exists():
        return 0
    cutoff = datetime.now().timestamp() - (max_age_days * 24 * 3600)
    deleted = 0
    for f in _REPORTS_DIR.glob("*.zip"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        except OSError:
            pass
    return deleted


@router.post("/upload", response_model=DiagnosticUploadResponse)
async def upload_diagnostic_report(
    request: Request,
    zip: UploadFile = File(..., description="ZIP del reporte generado por report_packager"),
    comment: str = Form("", description="Comentario del tecnico"),
    machine_id: str = Form("unknown", description="Machine ID del SGC"),
    hostname: str = Form("unknown", description="Hostname de la maquina"),
    app_version: str = Form("unknown", description="Version del SGC"),
):
    """Recibe un ZIP de reporte de diagnostico del SGC y lo reenvia por email.

    SIN AUTENTICACION: cualquier SGC puede subir un reporte de error.
    Esto es intencional para que el flujo sea sin friccion para el tecnico.

    Si SMTP no esta configurado, el ZIP se guarda igual y se loguea WARN.
    """
    # Validar nombre
    if not zip.filename or not zip.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser un .zip",
        )

    # Leer contenido (limite 50 MB)
    contents = await zip.read()
    if len(contents) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo ZIP está vacío o corrupto",
        )
    if len(contents) > _MAX_REPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera {_MAX_REPORT_BYTES // (1024 * 1024)} MB",
        )

    # Cleanup reportes viejos (90 dias) en cada upload (barato)
    try:
        _cleanup_old_reports(90)
    except Exception:
        pass

    # Guardar a disco con nombre unico
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_machine = (machine_id or "unknown").replace("/", "_")[:32]
    server_filename = f"diag_{safe_machine}_{stamp}.zip"
    zip_path = _REPORTS_DIR / server_filename
    zip_path.write_bytes(contents)

    # Loguear IP del cliente para debug
    client_ip = request.client.host if request.client else "unknown"
    log.info(
        f"Reporte de diagnostico recibido: {server_filename} "
        f"({len(contents)} bytes) desde {client_ip}, "
        f"machine={machine_id}, version={app_version}"
    )

    # Mandar email (no levanta excepcion si falla)
    email_sent = _send_report_email(
        zip_path=zip_path,
        comment=comment or "",
        machine_id=machine_id or "unknown",
        hostname=hostname or "unknown",
        app_version=app_version or "unknown",
    )

    return DiagnosticUploadResponse(
        ok=True,
        report_id=server_filename,
        email_sent=email_sent,
        size_bytes=len(contents),
        message="Reporte recibido y enviado al admin" if email_sent
                else "Reporte recibido (email no configurado, queda en server)",
    )


@router.get("/smtp-test-verbose")
async def smtp_test_verbose():
    """Test SMTP paso a paso para ver donde falla exactamente."""
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = os.environ.get("SMTP_PORT", "587").strip()
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()

    steps = []
    try:
        steps.append({"step": "1_connect", "msg": f"Conectando a {smtp_host}:{smtp_port}..."})
        server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=30)
        steps.append({"step": "1_connect", "ok": True})

        steps.append({"step": "2_ehlo", "msg": "EHLO..."})
        server.ehlo()
        steps.append({"step": "2_ehlo", "ok": True})

        steps.append({"step": "3_starttls", "msg": "STARTTLS..."})
        server.starttls()
        steps.append({"step": "3_starttls", "ok": True})

        steps.append({"step": "4_ehlo2", "msg": "EHLO post-TLS..."})
        server.ehlo()
        steps.append({"step": "4_ehlo2", "ok": True})

        steps.append({
            "step": "5_login",
            "msg": f"Login user={smtp_user!r} pass_len={len(smtp_pass)} "
                   f"pass_first_char={smtp_pass[0] if smtp_pass else ''} "
                   f"pass_last_char={smtp_pass[-1] if smtp_pass else ''}"
        })
        server.login(smtp_user, smtp_pass)
        steps.append({"step": "5_login", "ok": True})

        server.quit()
        return {"success": True, "steps": steps}
    except smtplib.SMTPAuthenticationError as e:
        steps.append({
            "step": "5_login",
            "ok": False,
            "error_code": e.smtp_code,
            "error_msg": e.smtp_error.decode('utf-8', errors='ignore') if e.smtp_error else str(e),
        })
        return {"success": False, "steps": steps}
    except Exception as e:
        steps.append({
            "step": "exception",
            "error_type": type(e).__name__,
            "error_msg": str(e),
        })
        return {"success": False, "steps": steps}


@router.get("/smtp-test")
async def smtp_test():
    """Manda un email de prueba al REPORT_DESTINATION y devuelve el error exacto.

    Usar SOLO para debug. Endpoint sin auth - no exponer en prod por mucho tiempo.
    """
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = os.environ.get("SMTP_PORT", "587").strip()
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()
    smtp_from = os.environ.get("SMTP_FROM", smtp_user).strip()
    dest = os.environ.get("REPORT_DESTINATION", "").strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "1").strip() != "0"

    if not (smtp_host and smtp_user and smtp_pass and dest):
        return {
            "success": False,
            "stage": "env_vars",
            "error": "Falta alguna env var",
            "have": {
                "SMTP_HOST": bool(smtp_host),
                "SMTP_USER": bool(smtp_user),
                "SMTP_PASSWORD": bool(smtp_pass),
                "REPORT_DESTINATION": bool(dest),
            },
        }

    try:
        msg = EmailMessage()
        msg["Subject"] = "[ESA625] SMTP Test - " + datetime.now().isoformat(timespec='seconds')
        msg["From"] = smtp_from
        msg["To"] = dest
        msg.set_content(
            "Este es un email de prueba del backend ESA625.\n"
            f"Hora: {datetime.now().isoformat(timespec='seconds')}\n"
            "Si llego este email, SMTP funciona OK."
        )

        port = int(smtp_port)
        if use_tls:
            with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        return {
            "success": True,
            "message": f"Email enviado a {dest}",
            "from": smtp_from,
            "host": smtp_host,
            "port": port,
        }
    except smtplib.SMTPAuthenticationError as e:
        return {
            "success": False,
            "stage": "auth",
            "error": f"Login fallo: {e.smtp_code} {e.smtp_error.decode('utf-8', errors='ignore') if e.smtp_error else ''}",
            "hint": "App Password mal o no es de la cuenta gmail dedicada. Verificar que SMTP_USER es la cuenta que generó la App Password.",
        }
    except smtplib.SMTPException as e:
        return {
            "success": False,
            "stage": "smtp",
            "error": f"{type(e).__name__}: {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "stage": "other",
            "error": f"{type(e).__name__}: {str(e)}",
        }


@router.get("/smtp-status")
async def smtp_status():
    """Verifica que env vars SMTP estan configuradas. No expone valores."""
    keys = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
            "SMTP_FROM", "REPORT_DESTINATION", "SMTP_USE_TLS"]
    result = {}
    for k in keys:
        raw = os.environ.get(k, "")
        v = raw.strip()
        # Diagnostico fino: detectar espacios, longitud antes/despues de strip
        result[k] = {
            "set": bool(v),
            "length_raw": len(raw),
            "length_stripped": len(v),
            "had_leading_space": raw != raw.lstrip(),
            "had_trailing_space": raw != raw.rstrip(),
            "has_internal_space": " " in v,
        }
        if k == "SMTP_PASSWORD":
            # Solo mostrar primer y ultimo char para verificar tipeo
            result[k]["preview"] = (
                f"{v[0]}***{v[-1]}" if len(v) >= 2 else ("***" if v else "(empty)")
            )
        else:
            # Para campos no sensibles mostrar mas chars
            result[k]["preview"] = (
                v[:5] + "..." + v[-5:]) if len(v) > 10 else v or "(empty)"

    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "REPORT_DESTINATION"]
    all_required_set = all(result[k]["set"] for k in required)
    result["__email_would_send__"] = all_required_set
    return result


@router.get("/list")
async def list_diagnostic_reports(
    limit: int = 50,
):
    """Listar reportes recibidos (utilidad para admin via curl/panel)."""
    if not _REPORTS_DIR.exists():
        return []
    files = sorted(
        _REPORTS_DIR.glob("*.zip"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]
    return [
        {
            "report_id": f.name,
            "size_bytes": f.stat().st_size,
            "received_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }
        for f in files
    ]
