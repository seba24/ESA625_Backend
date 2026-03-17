# -*- coding: utf-8 -*-
"""Schemas de autenticación."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    machine_id: str = ""


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company: str = ""
    machine_id: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    full_name: str
    credits: int


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    company: str
    credits: int
    is_active: bool

    model_config = {"from_attributes": True}
