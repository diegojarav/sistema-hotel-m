"""
Hotel Munich — Reportes Financieros Endpoints
===============================================
Daily income, transfer reconciliation, period summaries.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import Optional

from api.deps import get_db, get_current_user
from database import Transaccion
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/ingresos-diarios", summary="Ingresos del dia agrupado por metodo")
def ingresos_diarios(
    fecha: Optional[date] = Query(default=None, description="Fecha (default: hoy)"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Daily income grouped by payment method."""
    if fecha is None:
        fecha = date.today()

    start = datetime.combine(fecha, datetime.min.time())
    end = datetime.combine(fecha, datetime.max.time())

    transactions = db.query(Transaccion).filter(
        Transaccion.created_at >= start,
        Transaccion.created_at <= end,
        Transaccion.voided == False,
    ).all()

    totales = {"EFECTIVO": 0.0, "TRANSFERENCIA": 0.0, "POS": 0.0}
    conteos = {"EFECTIVO": 0, "TRANSFERENCIA": 0, "POS": 0}

    for t in transactions:
        if t.payment_method in totales:
            totales[t.payment_method] += t.amount
            conteos[t.payment_method] += 1

    return {
        "fecha": fecha.isoformat(),
        "efectivo": {"total": totales["EFECTIVO"], "count": conteos["EFECTIVO"]},
        "transferencia": {"total": totales["TRANSFERENCIA"], "count": conteos["TRANSFERENCIA"]},
        "pos": {"total": totales["POS"], "count": conteos["POS"]},
        "total_general": sum(totales.values()),
        "transacciones_total": len(transactions),
    }


@router.get("/transferencias", summary="Listado de transferencias para conciliacion")
def transferencias(
    desde: date = Query(...),
    hasta: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all TRANSFERENCIA transactions with reference numbers for bank reconciliation."""
    start = datetime.combine(desde, datetime.min.time())
    end = datetime.combine(hasta, datetime.max.time())

    transactions = db.query(Transaccion).filter(
        Transaccion.created_at >= start,
        Transaccion.created_at <= end,
        Transaccion.payment_method == "TRANSFERENCIA",
        Transaccion.voided == False,
    ).order_by(Transaccion.created_at.desc()).all()

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "total": sum(t.amount for t in transactions),
        "count": len(transactions),
        "transferencias": [
            {
                "id": t.id,
                "reserva_id": t.reserva_id,
                "amount": t.amount,
                "reference_number": t.reference_number or "",
                "description": t.description or "",
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "created_by": t.created_by or "",
            }
            for t in transactions
        ],
    }


@router.get("/resumen-periodo", summary="Resumen de ingresos por periodo")
def resumen_periodo(
    desde: date = Query(...),
    hasta: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Summary of income for a date range, broken down by payment method."""
    start = datetime.combine(desde, datetime.min.time())
    end = datetime.combine(hasta, datetime.max.time())

    transactions = db.query(Transaccion).filter(
        Transaccion.created_at >= start,
        Transaccion.created_at <= end,
        Transaccion.voided == False,
    ).all()

    totales = {"EFECTIVO": 0.0, "TRANSFERENCIA": 0.0, "POS": 0.0}
    conteos = {"EFECTIVO": 0, "TRANSFERENCIA": 0, "POS": 0}

    for t in transactions:
        if t.payment_method in totales:
            totales[t.payment_method] += t.amount
            conteos[t.payment_method] += 1

    total_general = sum(totales.values())
    total_count = sum(conteos.values())

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "total_general": total_general,
        "total_transacciones": total_count,
        "por_metodo": [
            {
                "metodo": metodo,
                "total": totales[metodo],
                "count": conteos[metodo],
                "porcentaje": round((totales[metodo] / total_general * 100) if total_general > 0 else 0, 1),
            }
            for metodo in ("EFECTIVO", "TRANSFERENCIA", "POS")
        ],
        "promedio_por_transaccion": round(total_general / total_count) if total_count > 0 else 0,
    }
