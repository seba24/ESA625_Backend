# -*- coding: utf-8 -*-
"""Configuración centralizada del backend."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_debug: bool = False
    app_version: str = "1.0.0"

    # Database
    database_url: str = "sqlite:///./esa625.db"

    # JWT
    jwt_secret_key: str = "change-this-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 horas

    # MercadoPago
    mercadopago_access_token: str = ""
    backend_url: str = "https://lionfish-app-58cxz.ondigitalocean.app"

    # CORS
    cors_origins: str = "http://localhost:8625,http://127.0.0.1:8625"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# #1526 SEGURIDAD: si falta JWT_SECRET_KEY se usaba el valor de ejemplo (que
# esta en este repo publico) y cualquiera podia fabricar una sesion de admin.
# Sin la variable, se usa una clave al azar: las sesiones se pierden al
# reiniciar el servidor, pero nadie puede falsificarlas.
_JWT_DE_EJEMPLO = "change-this-to-a-random-secret-key"

settings = Settings()
if not settings.jwt_secret_key or settings.jwt_secret_key == _JWT_DE_EJEMPLO:
    import logging as _logging
    import secrets as _secrets

    _logging.getLogger(__name__).critical(
        "#1526 JWT_SECRET_KEY no configurada: usando una clave al azar "
        "(las sesiones no sobreviven a un reinicio). Configurarla en DigitalOcean.")
    settings.jwt_secret_key = _secrets.token_hex(32)
