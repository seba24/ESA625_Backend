# -*- coding: utf-8 -*-
"""Schemas de reportes."""

from pydantic import BaseModel
from typing import Optional


class ReportUploadResponse(BaseModel):
    id: int
    module: str
    pdf_url: str
    credits_remaining: int
    message: str


class ReportListResponse(BaseModel):
    id: int
    module: str
    protocol_name: str
    client_name: str
    equipment_info: str
    credits_charged: int
    created_at: str

    model_config = {"from_attributes": True}
