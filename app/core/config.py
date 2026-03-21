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


settings = Settings()
