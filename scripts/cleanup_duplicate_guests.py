"""
One-time cleanup of duplicate Guest rows (v1.10.0 — Phase 2a follow-up).
=========================================================================

Why this exists
---------------
Migration 011 auto-populated the `guests` table from existing data with
two distinct passes:

  Pass A — One Guest per distinct CheckIn `document_number` (canonical).
  Pass B — One Guest per (property_id, guest_name) on reservations not
           covered by Pass A.

Pass B's name-key lookup didn't normalise the name string before matching,
so reservations whose `guest_name` carried an embedded document like
`"Acosta, Rosa (2362693)"` produced a SECOND Guest row alongside the clean
`(last="Acosta", first="Rosa", doc="2362693")` row created by Pass A.

This script merges those duplicates into a single canonical record per
person:

  1. Discover candidate clusters (same person, multiple Guest rows) by
     three signals:
       a. Same property_id + same document_number  (strongest)
       b. Same property_id + extracted-paren-doc matches another row's
          canonical document_number
       c. Same property_id + same normalised name (lower-cased + collapsed
          whitespace) where one row has a doc and the other has a paren-doc
          embedded in its name field
  2. Pick the keeper:
       - The row with the cleanest data (no parens, has doc) wins by default.
       - On tie, the one with more total_stays.
       - On further tie, the one created first.
  3. Re-link every reservation.guest_id and checkin.guest_id from the dupes
     to the keeper.
  4. Backfill the keeper with any non-empty fields from the dupes (never
     overwrite — keeper's data wins on conflict).
  5. Soft-delete the dupes (`is_active=False`) — never hard-delete, in case
     a stale FK we missed somewhere blows up. Hard-delete can come later.
  6. Recompute aggregates on the keeper.
  7. Print a per-cluster log line for the audit trail.

Usage
-----
    python scripts/cleanup_duplicate_guests.py                # apply
    python scripts/cleanup_duplicate_guests.py --dry-run      # show only

Idempotent — re-running after a clean DB is a no-op (zero clusters found).
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Make sibling `backend/` importable regardless of CWD
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from sqlalchemy import func, or_

from database import CheckIn, Guest, Reservation, SessionLocal  # noqa: E402
from services.guest_service import (  # noqa: E402
    _digits_only,
    _extract_embedded_doc,
    _norm_ws,
)


# ----------------------------------------------------------------------
# Cluster discovery
# ----------------------------------------------------------------------

def _name_key(g: Guest) -> str:
    """Normalised name key for clustering — strips parens, lowercases, collapses ws."""
    cleaned_first, _ = _extract_embedded_doc(g.first_name)
    cleaned_last, _ = _extract_embedded_doc(g.last_name)
    return f"{_norm_ws(cleaned_last).lower()}|{_norm_ws(cleaned_first).lower()}"


def _doc_or_extracted(g: Guest) -> Optional[str]:
    """Return the canonical doc — explicit column first, then paren-extracted."""
    if g.document_number and g.document_number.strip():
        return g.document_number.strip()
    for field in (g.first_name, g.last_name):
        _, extracted = _extract_embedded_doc(field)
        if extracted:
            return extracted
    return None


def _is_clean(g: Guest) -> bool:
    """A 'clean' guest has no embedded parens in name fields."""
    return "(" not in (g.first_name or "") and "(" not in (g.last_name or "")


def discover_clusters(db) -> List[List[Guest]]:
    """Group guests likely to be the same person.

    Two passes:
      A. by (property_id, doc_or_extracted) — STRONG
      B. by (property_id, name_key) for rows not yet bucketed — WEAK
    """
    all_guests = db.query(Guest).filter(Guest.is_active == True).all()  # noqa: E712

    by_doc: Dict[Tuple[str, str], List[Guest]] = defaultdict(list)
    leftovers: List[Guest] = []
    for g in all_guests:
        doc = _doc_or_extracted(g)
        if doc:
            by_doc[(g.property_id, doc)].append(g)
        else:
            leftovers.append(g)

    clusters: List[List[Guest]] = []
    for cluster in by_doc.values():
        if len(cluster) > 1:
            clusters.append(cluster)

    # Pass B — among leftovers (no doc anywhere), bucket by name
    by_name: Dict[Tuple[str, str], List[Guest]] = defaultdict(list)
    for g in leftovers:
        by_name[(g.property_id, _name_key(g))].append(g)
    for cluster in by_name.values():
        if len(cluster) > 1:
            clusters.append(cluster)

    return clusters


# ----------------------------------------------------------------------
# Keeper selection
# ----------------------------------------------------------------------

def choose_keeper(cluster: List[Guest]) -> Guest:
    """Sort by: clean-name, total_stays DESC, has-doc-explicit, oldest first."""
    def sort_key(g: Guest):
        return (
            0 if _is_clean(g) else 1,
            -(g.total_stays or 0),
            0 if (g.document_number and g.document_number.strip()) else 1,
            g.created_at or datetime.max,
        )
    return sorted(cluster, key=sort_key)[0]


# ----------------------------------------------------------------------
# Merge
# ----------------------------------------------------------------------

def merge_cluster(db, cluster: List[Guest], dry_run: bool) -> Dict[str, int]:
    """Merge `cluster` into a single keeper. Returns counts of changes."""
    keeper = choose_keeper(cluster)
    dupes = [g for g in cluster if g.id != keeper.id]
    counts = {"reservations_relinked": 0, "checkins_relinked": 0, "dupes_deactivated": 0}

    for dupe in dupes:
        # Re-link reservations
        n_res = (
            db.query(Reservation)
            .filter(Reservation.guest_id == dupe.id)
            .update({Reservation.guest_id: keeper.id}, synchronize_session=False)
        )
        counts["reservations_relinked"] += n_res

        # Re-link checkins
        n_ci = (
            db.query(CheckIn)
            .filter(CheckIn.guest_id == dupe.id)
            .update({CheckIn.guest_id: keeper.id}, synchronize_session=False)
        )
        counts["checkins_relinked"] += n_ci

        # Backfill keeper from dupe — only fill empty fields
        for col in (
            "document_type", "document_number", "email", "phone",
            "nationality", "country", "city", "notes",
        ):
            keeper_val = (getattr(keeper, col) or "").strip() if isinstance(getattr(keeper, col), str) else getattr(keeper, col)
            dupe_val = getattr(dupe, col)
            if not keeper_val and dupe_val and (not isinstance(dupe_val, str) or dupe_val.strip()):
                setattr(keeper, col, dupe_val)

        # If the keeper's own name is "dirty" but the dupe has a clean name,
        # adopt the clean form (this handles the Acosta/Aquino case where the
        # dupe has the embedded paren and we need the keeper's clean name).
        # We chose keeper for clean-name first, but be defensive.
        if not _is_clean(keeper) and _is_clean(dupe):
            keeper.first_name = dupe.first_name
            keeper.last_name = dupe.last_name

        # Deactivate dupe (soft-delete, history preserved)
        dupe.is_active = False
        dupe.notes = (dupe.notes or "") + f"\n[merged into guest #{keeper.id} on {datetime.now().isoformat(timespec='seconds')}]"
        counts["dupes_deactivated"] += 1

    # Cleanup: even if keeper survived, ensure its name is clean
    cleaned_first, embedded_first = _extract_embedded_doc(keeper.first_name)
    cleaned_last, embedded_last = _extract_embedded_doc(keeper.last_name)
    if cleaned_first != (keeper.first_name or "").strip():
        keeper.first_name = cleaned_first or "(sin nombre)"
    if cleaned_last != (keeper.last_name or "").strip():
        keeper.last_name = cleaned_last or "(sin apellido)"
    extracted_doc = embedded_first or embedded_last
    if extracted_doc and not (keeper.document_number or "").strip():
        keeper.document_number = extracted_doc

    if dry_run:
        db.rollback()
    else:
        db.commit()
        # Recompute keeper aggregates from the now-updated reservation links
        from services.guest_service import GuestService
        try:
            GuestService.refresh_aggregates(db=db, guest_id=keeper.id)
        except Exception as e:
            print(f"  [warn] refresh_aggregates(guest #{keeper.id}) failed: {e}")

    return {"keeper_id": keeper.id, **counts}


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Merge duplicate Guest rows. Idempotent."
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; no DB changes.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        clusters = discover_clusters(db)
        if not clusters:
            print("[OK] No duplicate guest clusters detected. Nothing to do.")
            return

        print(f"[INFO] Found {len(clusters)} duplicate cluster(s).")
        if args.dry_run:
            print("[INFO] DRY-RUN: no changes will be committed.")

        total = {"reservations_relinked": 0, "checkins_relinked": 0, "dupes_deactivated": 0}

        for i, cluster in enumerate(clusters, 1):
            print(f"\n--- Cluster #{i} ({len(cluster)} guests, property={cluster[0].property_id}) ---")
            for g in cluster:
                doc = _doc_or_extracted(g)
                clean = "yes" if _is_clean(g) else "no (paren in name)"
                print(
                    f"  Guest #{g.id} | {g.last_name!r}, {g.first_name!r} | "
                    f"doc={doc} | stays={g.total_stays} | spent={g.total_spent} | clean={clean}"
                )
            result = merge_cluster(db, cluster, dry_run=args.dry_run)
            print(
                f"  -> keeper=Guest #{result['keeper_id']} | "
                f"relinked {result['reservations_relinked']} reservations + "
                f"{result['checkins_relinked']} checkins | "
                f"deactivated {result['dupes_deactivated']} dupe(s)"
            )
            for k in total:
                total[k] += result[k]

        print()
        print("=" * 60)
        print(f"[SUMMARY] Clusters processed: {len(clusters)}")
        print(f"[SUMMARY] Reservations relinked: {total['reservations_relinked']}")
        print(f"[SUMMARY] Checkins relinked: {total['checkins_relinked']}")
        print(f"[SUMMARY] Duplicates deactivated: {total['dupes_deactivated']}")
        if args.dry_run:
            print("[SUMMARY] DRY-RUN — no changes persisted.")
        else:
            print("[SUMMARY] Changes committed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
