# -*- coding: utf-8 -*-
"""Endpoints de créditos."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.report import CreditTransaction

router = APIRouter(prefix="/credits", tags=["credits"])


class CreditBalanceResponse(BaseModel):
    credits: int
    user_id: int


class TransactionResponse(BaseModel):
    id: int
    amount: int
    balance_after: int
    description: str
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/balance", response_model=CreditBalanceResponse)
def get_balance(user: User = Depends(get_current_user)):
    """Obtener saldo de créditos del usuario."""
    return CreditBalanceResponse(credits=user.credits, user_id=user.id)


@router.get("/history", response_model=List[TransactionResponse])
def get_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Historial de transacciones de créditos."""
    txns = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.user_id == user.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        TransactionResponse(
            id=t.id,
            amount=t.amount,
            balance_after=t.balance_after,
            description=t.description,
            created_at=t.created_at.isoformat(),
        )
        for t in txns
    ]
