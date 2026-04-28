"""
BillingProfileService — invoice profiles per Guest (v1.10.0 — Phase 2a-ext).
============================================================================

Manages the `billing_profiles` table. A guest can carry multiple profiles
(personal CI, corporate RUC + Razón Social, cross-border CUIT/CPF/CNPJ).

The legacy `checkins.billing_name` + `checkins.billing_ruc` columns are kept
as the per-stay snapshot. The BillingProfile is the *living* version reused
across stays via `checkins.billing_profile_id`.

`is_default` semantics
----------------------
At most one profile per guest may be the default. The recepcionist marks
one explicitly (or the migration 013 backfill nominates the first one
seen). The default auto-selects in the checkin form unless overridden.
`set_default` clears the flag on all sibling profiles in the same
transaction so we never end up with two defaults.

`find_or_create_from_checkin`
-----------------------------
Lookup priority:
  1. Same (guest_id, tax_id_number) — tax_id is canonical
  2. Same (guest_id, business_name) — fallback when no tax_id
  3. Otherwise create
Used by the checkin flow: when the user types billing data without picking
from the dropdown, this creates / finds a profile transparently.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import BillingProfile, Guest
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class BillingProfileError(Exception):
    """Raised on BillingProfile business-rule violations (Spanish messages)."""


class BillingProfileService:

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def create_profile(
        db: Session,
        guest_id: int,
        property_id: str,
        data: Dict[str, Any],
    ) -> BillingProfile:
        """Create a new profile attached to `guest_id` under `property_id`."""
        guest = db.query(Guest).filter(Guest.id == guest_id).first()
        if guest is None:
            raise BillingProfileError(f"No existe huésped con id {guest_id}")
        if guest.property_id != property_id:
            raise BillingProfileError(
                f"El huésped {guest_id} pertenece a otra propiedad"
            )

        prof = BillingProfile(
            guest_id=guest_id,
            property_id=property_id,
            label=_strip_or_none(data.get("label")),
            is_default=bool(data.get("is_default", False)),
            tax_id_type=_strip_or_none(data.get("tax_id_type")),
            tax_id_number=_strip_or_none(data.get("tax_id_number")),
            business_name=_strip_or_none(data.get("business_name")),
            address=_strip_or_none(data.get("address")),
            city=_strip_or_none(data.get("city")),
            state=_strip_or_none(data.get("state")),
            country=_strip_or_none(data.get("country")),
            is_active=True,
        )
        # If marked default, clear flag on siblings in the same insert.
        if prof.is_default:
            _clear_default_flag(db, guest_id)
        db.add(prof)
        db.commit()
        db.refresh(prof)
        logger.info(
            f"Created BillingProfile #{prof.id} for guest #{guest_id} "
            f"(label={prof.label!r}, default={prof.is_default})"
        )
        return prof

    @staticmethod
    @with_db
    def get_profile(db: Session, profile_id: int) -> Optional[BillingProfile]:
        return db.query(BillingProfile).filter(BillingProfile.id == profile_id).first()

    @staticmethod
    @with_db
    def get_profiles(
        db: Session,
        guest_id: int,
        active_only: bool = True,
    ) -> List[BillingProfile]:
        """All profiles for `guest_id`, default first then created order."""
        q = db.query(BillingProfile).filter(BillingProfile.guest_id == guest_id)
        if active_only:
            q = q.filter(BillingProfile.is_active == True)  # noqa: E712
        return (
            q.order_by(BillingProfile.is_default.desc(), BillingProfile.created_at)
            .all()
        )

    @staticmethod
    @with_db
    def update_profile(
        db: Session,
        profile_id: int,
        data: Dict[str, Any],
    ) -> Optional[BillingProfile]:
        prof = db.query(BillingProfile).filter(BillingProfile.id == profile_id).first()
        if prof is None:
            return None
        for col in (
            "label", "tax_id_type", "tax_id_number", "business_name",
            "address", "city", "state", "country",
        ):
            if col in data:
                val = data[col]
                if isinstance(val, str):
                    val = val.strip() or None
                setattr(prof, col, val)

        if "is_default" in data and data["is_default"] is not None:
            new_default = bool(data["is_default"])
            if new_default and not prof.is_default:
                _clear_default_flag(db, prof.guest_id)
            prof.is_default = new_default

        if "is_active" in data and data["is_active"] is not None:
            prof.is_active = bool(data["is_active"])

        prof.updated_at = datetime.now()
        db.commit()
        db.refresh(prof)
        return prof

    @staticmethod
    @with_db
    def delete_profile(db: Session, profile_id: int) -> bool:
        """Soft delete (sets is_active=False). Returns True if found."""
        prof = db.query(BillingProfile).filter(BillingProfile.id == profile_id).first()
        if prof is None:
            return False
        prof.is_active = False
        # Don't leave a soft-deleted row as the default.
        prof.is_default = False
        prof.updated_at = datetime.now()
        db.commit()
        return True

    @staticmethod
    @with_db
    def set_default(db: Session, guest_id: int, profile_id: int) -> Optional[BillingProfile]:
        """Mark `profile_id` as the default for `guest_id`, clearing siblings."""
        prof = (
            db.query(BillingProfile)
            .filter(BillingProfile.id == profile_id, BillingProfile.guest_id == guest_id)
            .first()
        )
        if prof is None:
            return None
        if not prof.is_active:
            raise BillingProfileError("No se puede marcar como predeterminado un perfil inactivo")
        _clear_default_flag(db, guest_id)
        prof.is_default = True
        prof.updated_at = datetime.now()
        db.commit()
        db.refresh(prof)
        return prof

    # ------------------------------------------------------------------
    # find-or-create from checkin form data
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def find_or_create_from_checkin(
        db: Session,
        guest_id: int,
        property_id: str,
        razon_social: Optional[str],
        ruc: Optional[str],
    ) -> Optional[BillingProfile]:
        """Used by the checkin flow when billing data is typed in the form
        without explicit profile selection.

        Match priority (highest → lowest):
          1. (guest_id, tax_id_number) — tax_id is canonical
          2. (guest_id, business_name) — fallback when no tax_id
          3. Otherwise create

        Returns the profile (existing or new), or None if both `razon_social`
        and `ruc` are blank (nothing to identify the profile with).
        """
        rs = (razon_social or "").strip() or None
        tx = (ruc or "").strip() or None
        if not rs and not tx:
            return None

        try:
            base = (
                db.query(BillingProfile)
                .filter(BillingProfile.guest_id == guest_id)
                .filter(BillingProfile.is_active == True)  # noqa: E712
            )
            hit: Optional[BillingProfile] = None
            if tx:
                hit = base.filter(BillingProfile.tax_id_number == tx).first()
            if hit is None and rs:
                hit = base.filter(BillingProfile.business_name == rs).first()
            if hit is not None:
                # Augment empty fields (e.g. existing has tax_id but no name)
                changed = False
                if rs and not (hit.business_name or "").strip():
                    hit.business_name = rs
                    changed = True
                if tx and not (hit.tax_id_number or "").strip():
                    hit.tax_id_number = tx
                    changed = True
                if changed:
                    hit.updated_at = datetime.now()
                    db.commit()
                    db.refresh(hit)
                return hit

            # Brand new profile — first one becomes the default automatically
            existing_count = (
                db.query(BillingProfile)
                .filter(
                    BillingProfile.guest_id == guest_id,
                    BillingProfile.is_active == True,  # noqa: E712
                )
                .count()
            )
            return BillingProfileService.create_profile(
                db=db,
                guest_id=guest_id,
                property_id=property_id,
                data={
                    "business_name": rs,
                    "tax_id_number": tx,
                    "tax_id_type": "RUC" if tx else None,
                    "is_default": existing_count == 0,
                },
            )
        except BillingProfileError:
            raise
        except Exception as e:
            logger.warning(f"find_or_create_from_checkin failed: {e}", exc_info=True)
            return None


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _strip_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _clear_default_flag(db: Session, guest_id: int) -> None:
    """Set is_default=False on every active profile of `guest_id`.

    Service-layer enforcement of the "at most one default per guest" rule.
    Caller is responsible for then setting the new default + committing.
    """
    db.query(BillingProfile).filter(
        BillingProfile.guest_id == guest_id,
        BillingProfile.is_default == True,  # noqa: E712
    ).update({BillingProfile.is_default: False}, synchronize_session=False)
