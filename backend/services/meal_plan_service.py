"""
Meal Plan Service (v1.7.0 — Phase 4)
=====================================

CRUD + seeding for the `meal_plans` catalog. Used by the reservation form
(plan dropdown) and the PC admin "Configuración de Comidas" page.

Business rules
--------------
- Non-negative surcharges.
- Unique `(property_id, code)`.
- `is_system=1` plans are protected from deletion (only soft-deactivate via admin).
- `SOLO_HABITACION` is always available (seeded during migration 005 and re-seeded
  here for safety if missing).
- When `meal_inclusion_mode` changes, `seed_system_plans()` auto-inserts any
  missing standard plans.
"""

import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from database import MealPlan
from services._base import with_db
from logging_config import get_logger

logger = get_logger(__name__)


class MealPlanError(Exception):
    """Raised on validation failures in MealPlanService."""


class MealPlanService:
    """CRUD for meal plans + seed helpers."""

    # ---- Helpers ------------------------------------------------------
    @staticmethod
    def _to_dict(plan: MealPlan) -> Dict[str, Any]:
        return {
            "id": plan.id,
            "property_id": plan.property_id,
            "code": plan.code,
            "name": plan.name,
            "description": plan.description,
            "surcharge_per_person": float(plan.surcharge_per_person or 0),
            "surcharge_per_room": float(plan.surcharge_per_room or 0),
            "applies_to_mode": plan.applies_to_mode,
            "is_system": bool(plan.is_system),
            "is_active": bool(plan.is_active),
            "sort_order": plan.sort_order or 0,
        }

    # ---- Queries ------------------------------------------------------
    @staticmethod
    @with_db
    def list_plans(
        db: Session,
        property_id: str = "los-monges",
        mode_filter: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        """List meal plans. `mode_filter` narrows to plans that apply under the
        given hotel mode: returns plans with applies_to_mode IN (ANY, <mode>)."""
        q = db.query(MealPlan).filter(MealPlan.property_id == property_id)
        if not include_inactive:
            q = q.filter(MealPlan.is_active == 1)
        if mode_filter:
            q = q.filter(MealPlan.applies_to_mode.in_([mode_filter, "ANY"]))
        plans = q.order_by(MealPlan.sort_order, MealPlan.name).all()
        return [MealPlanService._to_dict(p) for p in plans]

    @staticmethod
    @with_db
    def get_plan(db: Session, plan_id: str) -> Optional[Dict[str, Any]]:
        p = db.query(MealPlan).filter(MealPlan.id == plan_id).first()
        return MealPlanService._to_dict(p) if p else None

    @staticmethod
    @with_db
    def get_plan_by_code(db: Session, property_id: str, code: str) -> Optional[Dict[str, Any]]:
        p = (
            db.query(MealPlan)
            .filter(MealPlan.property_id == property_id, MealPlan.code == code)
            .first()
        )
        return MealPlanService._to_dict(p) if p else None

    # ---- Mutations ----------------------------------------------------
    @staticmethod
    @with_db
    def create_plan(
        db: Session,
        property_id: str,
        code: str,
        name: str,
        surcharge_per_person: float = 0.0,
        surcharge_per_room: float = 0.0,
        applies_to_mode: str = "ANY",
        description: Optional[str] = None,
        sort_order: int = 0,
        is_system: bool = False,
    ) -> Dict[str, Any]:
        MealPlanService._validate(code, name, surcharge_per_person, surcharge_per_room, applies_to_mode)
        # Uniqueness check
        existing = (
            db.query(MealPlan)
            .filter(MealPlan.property_id == property_id, MealPlan.code == code)
            .first()
        )
        if existing:
            raise MealPlanError(f"Ya existe un plan con código '{code}'.")

        plan = MealPlan(
            id=str(uuid.uuid4()),
            property_id=property_id,
            code=code.strip().upper(),
            name=name.strip(),
            description=description,
            surcharge_per_person=float(surcharge_per_person),
            surcharge_per_room=float(surcharge_per_room),
            applies_to_mode=applies_to_mode,
            is_system=1 if is_system else 0,
            is_active=1,
            sort_order=sort_order,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        logger.info(f"MealPlan created: {plan.code} for {property_id}")
        return MealPlanService._to_dict(plan)

    @staticmethod
    @with_db
    def update_plan(db: Session, plan_id: str, **updates) -> Dict[str, Any]:
        plan = db.query(MealPlan).filter(MealPlan.id == plan_id).first()
        if not plan:
            raise MealPlanError(f"Plan no encontrado: {plan_id}")

        # Validate provided updates
        if "surcharge_per_person" in updates and updates["surcharge_per_person"] < 0:
            raise MealPlanError("Recargo por persona no puede ser negativo.")
        if "surcharge_per_room" in updates and updates["surcharge_per_room"] < 0:
            raise MealPlanError("Recargo por habitación no puede ser negativo.")
        if "applies_to_mode" in updates and updates["applies_to_mode"] not in {
            "ANY", "INCLUIDO", "OPCIONAL_PERSONA", "OPCIONAL_HABITACION"
        }:
            raise MealPlanError(f"Modo inválido: {updates['applies_to_mode']}")

        # System plans: can be edited (name/surcharge tweaks) but code is frozen
        if plan.is_system and "code" in updates and updates["code"] != plan.code:
            raise MealPlanError("No se puede cambiar el código de un plan del sistema.")

        allowed = {"name", "description", "surcharge_per_person", "surcharge_per_room",
                   "applies_to_mode", "sort_order", "is_active", "code"}
        for key, value in updates.items():
            if key in allowed and value is not None:
                setattr(plan, key, value)
        db.commit()
        db.refresh(plan)
        return MealPlanService._to_dict(plan)

    @staticmethod
    @with_db
    def soft_delete(db: Session, plan_id: str) -> bool:
        plan = db.query(MealPlan).filter(MealPlan.id == plan_id).first()
        if not plan:
            raise MealPlanError(f"Plan no encontrado: {plan_id}")
        if plan.is_system:
            raise MealPlanError("No se puede eliminar un plan del sistema. Desactívelo si ya no se usa.")
        plan.is_active = 0
        db.commit()
        logger.info(f"MealPlan soft-deleted: {plan.code}")
        return True

    # ---- Seeding ------------------------------------------------------
    @staticmethod
    @with_db
    def seed_system_plans(db: Session, property_id: str, mode: Optional[str]) -> Dict[str, int]:
        """Ensure mandatory system plans exist for a given property + mode.

        - SOLO_HABITACION is always seeded (ANY mode, zero surcharge).
        - For mode=INCLUIDO, CON_DESAYUNO is seeded with zero surcharge
          (reservation form stays hidden; kitchen report counts all guests).
        """
        seeded = {"solo_habitacion": 0, "con_desayuno": 0}

        # SOLO_HABITACION
        existing = (
            db.query(MealPlan)
            .filter(MealPlan.property_id == property_id, MealPlan.code == "SOLO_HABITACION")
            .first()
        )
        if not existing:
            db.add(MealPlan(
                id=str(uuid.uuid4()),
                property_id=property_id,
                code="SOLO_HABITACION",
                name="Solo habitación",
                surcharge_per_person=0.0,
                surcharge_per_room=0.0,
                applies_to_mode="ANY",
                is_system=1,
                is_active=1,
                sort_order=0,
            ))
            seeded["solo_habitacion"] = 1

        # CON_DESAYUNO (only for INCLUIDO mode)
        if mode == "INCLUIDO":
            existing = (
                db.query(MealPlan)
                .filter(MealPlan.property_id == property_id, MealPlan.code == "CON_DESAYUNO")
                .first()
            )
            if not existing:
                db.add(MealPlan(
                    id=str(uuid.uuid4()),
                    property_id=property_id,
                    code="CON_DESAYUNO",
                    name="Con desayuno (incluido)",
                    surcharge_per_person=0.0,
                    surcharge_per_room=0.0,
                    applies_to_mode="INCLUIDO",
                    is_system=1,
                    is_active=1,
                    sort_order=1,
                ))
                seeded["con_desayuno"] = 1
            else:
                # Hotel is now in INCLUIDO mode → realign any pre-existing
                # CON_DESAYUNO plan to reflect it: zero surcharge, mode=INCLUIDO,
                # active. Otherwise the admin UI would show stale per-person
                # surcharges that are ignored by the pricing engine anyway —
                # confusing. Pricing-engine-side we already gate on the hotel's
                # mode, but the UI should match what's actually applied.
                existing.surcharge_per_person = 0.0
                existing.surcharge_per_room = 0.0
                existing.applies_to_mode = "INCLUIDO"
                existing.is_active = 1
                existing.is_system = 1

        db.commit()
        if sum(seeded.values()) > 0:
            logger.info(f"Seeded system meal plans for {property_id}: {seeded}")
        return seeded

    # ---- Validation ---------------------------------------------------
    @staticmethod
    def _validate(code: str, name: str, sp_pp: float, sp_room: float, mode: str) -> None:
        if not code or not code.strip():
            raise MealPlanError("Código del plan es requerido.")
        if not name or not name.strip():
            raise MealPlanError("Nombre del plan es requerido.")
        if sp_pp < 0 or sp_room < 0:
            raise MealPlanError("Los recargos no pueden ser negativos.")
        if mode not in {"ANY", "INCLUIDO", "OPCIONAL_PERSONA", "OPCIONAL_HABITACION"}:
            raise MealPlanError(f"Modo inválido: {mode}")
