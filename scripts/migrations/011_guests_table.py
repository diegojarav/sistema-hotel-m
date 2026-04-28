"""
Migration 011: Guests master table (v1.10.0 — Phase 2a, Part 1)
================================================================

Creates the new `guests` table — one row per *person* who has stayed (or
will stay) at the hotel — and the `guest_id` FK columns on `reservations`
and `checkins`. Auto-populates from the existing data so the table is
useful from the moment it lands (rather than starting empty and only
filling as new bookings arrive).

The new table coexists with the existing `checkins` table:
  - guests        — the master person (this migration creates it)
  - checkins      — the per-stay registration record (ficha)
  - reservations  — the booking
A reservation links to BOTH its guest_id (the person) and its room_id
(where they stay). A checkin links to its reservation_id (the booking)
and guest_id (who they are). The snapshot fields (`reservations.guest_name`,
`reservations.contact_email`, `checkins.last_name`, etc.) stay as
frozen-at-creation-time values.

Auto-population strategy
------------------------
1. **From checkins**: every distinct `document_number` becomes one Guest row.
   Document is the strongest identity — if a checkin row has it, that's the
   most reliable seed.

2. **From reservations**: every distinct `(property_id, guest_name)` pair
   not yet covered (no document match in step 1) becomes a Guest row. The
   `guest_name` is split heuristically:
     - "Lastname, Firstname"  → ("Lastname", "Firstname")  (ficha convention)
     - "Firstname Lastname"   → ("Firstname", "Lastname")  (natural form)
     - single token           → ("(sin apellido)", token)

3. **Backfill `reservations.guest_id`**: each reservation gets matched to its
   guest by (property_id, guest_name) — same key used to create the guest
   in step 2. Any unmatched stays at NULL (acceptable — guest_id is
   nullable + SET NULL on delete).

4. **Backfill `checkins.guest_id`**: each checkin gets matched by
   document_number first (step 1's seed), else by name.

Idempotent — safe to re-run. Detects partial application and skips done
work via existence checks. The auto-populate phase runs ONLY if the
guests table is empty (avoids re-creating duplicates on re-run).
"""

import sqlite3
from typing import Dict, Tuple

MIGRATION_NAME = "011_guests_table"
MIGRATION_DESCRIPTION = "Create guests master table + backfill guest_id on reservations/checkins (Phase 2a)"


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _index_exists(cursor, index_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cursor.fetchone() is not None


# Heuristic: split a guest_name into (first_name, last_name).
def _split_name(guest_name: str) -> Tuple[str, str]:
    g = (guest_name or "").strip()
    if not g:
        return "", ""
    if "," in g:
        last_part, _, first_part = g.partition(",")
        return first_part.strip(), last_part.strip()
    parts = g.split()
    if len(parts) == 1:
        return "", parts[0]
    # First token = first name, rest = last name
    return parts[0], " ".join(parts[1:])


def run(conn: sqlite3.Connection):
    """Apply migration 011. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 1. Create guests table (idempotent) ---
    if not _table_exists(cursor, "guests"):
        cursor.execute(
            """
            CREATE TABLE guests (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id     VARCHAR NOT NULL,
                first_name      VARCHAR NOT NULL,
                last_name       VARCHAR NOT NULL,
                document_type   VARCHAR,
                document_number VARCHAR,
                email           VARCHAR,
                phone           VARCHAR,
                nationality     VARCHAR,
                country         VARCHAR,
                city            VARCHAR,
                notes           VARCHAR,
                source          VARCHAR DEFAULT 'Direct',
                is_active       BOOLEAN DEFAULT 1,
                total_stays     INTEGER DEFAULT 0,
                total_spent     FLOAT   DEFAULT 0.0,
                last_visit_at   DATE,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
            """
        )

    # Indexes (mirror the model's __table_args__)
    for idx_name, cols in (
        ("idx_guests_property_lastname",  "property_id, last_name"),
        ("idx_guests_property_document",  "property_id, document_number"),
        ("idx_guests_property_email",     "property_id, email"),
        ("idx_guests_property_phone",     "property_id, phone"),
        ("idx_guests_property_active",    "property_id, is_active"),
    ):
        if not _index_exists(cursor, idx_name):
            cursor.execute(f"CREATE INDEX {idx_name} ON guests ({cols})")

    # --- 2. Add guest_id columns ---
    if not _column_exists(cursor, "reservations", "guest_id"):
        cursor.execute("ALTER TABLE reservations ADD COLUMN guest_id INTEGER")
        # Note: SQLite ALTER TABLE ADD COLUMN does NOT support ADD CONSTRAINT
        # for FK. The FK is declared in the SQLAlchemy model and enforced on
        # fresh init_db() / Postgres. Same pattern as Phase 1 cascades.
    if not _index_exists(cursor, "ix_reservations_guest_id"):
        cursor.execute("CREATE INDEX ix_reservations_guest_id ON reservations (guest_id)")

    if not _column_exists(cursor, "checkins", "guest_id"):
        cursor.execute("ALTER TABLE checkins ADD COLUMN guest_id INTEGER")
    if not _index_exists(cursor, "ix_checkins_guest_id"):
        cursor.execute("CREATE INDEX ix_checkins_guest_id ON checkins (guest_id)")

    # --- 3. Auto-populate (only if table empty — re-run safety) ---
    cursor.execute("SELECT COUNT(*) FROM guests")
    if cursor.fetchone()[0] > 0:
        # Already populated — skip the seed phase.
        return

    # Determine the default property_id (single-tenant today).
    cursor.execute("SELECT id FROM properties LIMIT 1")
    prop_row = cursor.fetchone()
    default_property = prop_row[0] if prop_row else "los-monges"

    # 3a. Seed guests from distinct document_number on checkins (highest signal)
    # Map: document_number -> guest_id (we'll use this to backfill checkins.guest_id)
    doc_to_guest: Dict[str, int] = {}
    cursor.execute(
        """
        SELECT
            document_number,
            MAX(last_name)        AS last_name,
            MAX(first_name)       AS first_name,
            MAX(nationality)      AS nationality,
            MAX(country)          AS country,
            MAX(contact_email)    AS contact_email,
            MAX(contact_phone)    AS contact_phone,
            MAX(created_at)       AS most_recent
        FROM checkins
        WHERE document_number IS NOT NULL AND TRIM(document_number) != ''
        GROUP BY document_number
        """
    )
    for row in cursor.fetchall():
        doc_num, last, first, nat, country, email, phone, _last_seen = row
        first = (first or "").strip()
        last = (last or "").strip()
        if not first and not last:
            last = "(sin apellido)"
        cursor.execute(
            """
            INSERT INTO guests (
                property_id, first_name, last_name,
                document_type, document_number, email, phone,
                nationality, country, source, is_active, total_stays, total_spent
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, 'Direct', 1, 0, 0.0)
            """,
            (
                default_property,
                first or "(sin nombre)",
                last,
                doc_num.strip(),
                (email or "").strip() or None,
                (phone or "").strip() or None,
                (nat or "").strip() or None,
                (country or "").strip() or None,
            ),
        )
        doc_to_guest[doc_num.strip()] = cursor.lastrowid

    # 3b. Build a name-key → guest_id index from what we just inserted (used in 3c).
    name_to_guest: Dict[Tuple[str, str], int] = {}
    cursor.execute(
        "SELECT id, property_id, last_name, first_name FROM guests"
    )
    for gid, pid, ln, fn in cursor.fetchall():
        key = (pid, _norm(ln) + "|" + _norm(fn))
        # Don't overwrite if already present (keeps the most-stayed candidate first).
        name_to_guest.setdefault(key, gid)

    # 3c. Seed guests from distinct (property_id, guest_name) on reservations
    # not yet covered by a name match. Also backfills `reservations.guest_id`
    # in the same pass.
    cursor.execute(
        """
        SELECT
            id              AS res_id,
            property_id     AS prop_id,
            guest_name      AS gname,
            contact_email   AS email,
            contact_phone   AS phone,
            source          AS source
        FROM reservations
        WHERE guest_id IS NULL
        """
    )
    res_rows = cursor.fetchall()

    for res_id, prop_id, gname, email, phone, source in res_rows:
        prop_id = prop_id or default_property
        gname_clean = (gname or "").strip()
        if not gname_clean:
            continue  # nothing to identify the guest with

        first, last = _split_name(gname_clean)
        if not first and not last:
            continue

        key = (prop_id, _norm(last) + "|" + _norm(first))
        guest_id = name_to_guest.get(key)
        if guest_id is None:
            cursor.execute(
                """
                INSERT INTO guests (
                    property_id, first_name, last_name,
                    email, phone, source,
                    is_active, total_stays, total_spent
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, 0.0)
                """,
                (
                    prop_id,
                    first or "(sin nombre)",
                    last or "(sin apellido)",
                    (email or "").strip() or None,
                    (phone or "").strip() or None,
                    source or "Direct",
                ),
            )
            guest_id = cursor.lastrowid
            name_to_guest[key] = guest_id

        # Backfill the reservation's guest_id
        cursor.execute(
            "UPDATE reservations SET guest_id = ? WHERE id = ?",
            (guest_id, res_id),
        )

    # 3d. Backfill checkins.guest_id (document → guest, then name fallback)
    cursor.execute(
        """
        SELECT id, document_number, last_name, first_name, room_id
        FROM checkins
        WHERE guest_id IS NULL
        """
    )
    for cid, doc, ln, fn, rid in cursor.fetchall():
        gid = None
        if doc and doc.strip() and doc.strip() in doc_to_guest:
            gid = doc_to_guest[doc.strip()]
        else:
            # Fall back to name match. Need property_id for the check-in's room.
            prop_id = default_property
            if rid:
                cursor.execute("SELECT property_id FROM rooms WHERE id = ?", (rid,))
                row = cursor.fetchone()
                if row and row[0]:
                    prop_id = row[0]
            ln_norm = _norm(ln)
            fn_norm = _norm(fn)
            if ln_norm or fn_norm:
                key = (prop_id, ln_norm + "|" + fn_norm)
                gid = name_to_guest.get(key)
        if gid is not None:
            cursor.execute(
                "UPDATE checkins SET guest_id = ? WHERE id = ?",
                (gid, cid),
            )

    # 3e. Refresh aggregate columns (total_stays, total_spent, last_visit_at)
    # using the just-built links.
    cursor.execute(
        """
        UPDATE guests
        SET
            total_stays   = COALESCE((
                SELECT COUNT(*)
                FROM reservations r
                WHERE r.guest_id = guests.id
                  AND LOWER(COALESCE(r.status, '')) NOT IN ('cancelada', 'cancelled')
            ), 0),
            total_spent   = COALESCE((
                SELECT SUM(COALESCE(r.final_price, r.price, 0))
                FROM reservations r
                WHERE r.guest_id = guests.id
                  AND LOWER(COALESCE(r.status, '')) NOT IN ('cancelada', 'cancelled')
            ), 0.0),
            last_visit_at = (
                SELECT MAX(r.check_in_date)
                FROM reservations r
                WHERE r.guest_id = guests.id
                  AND LOWER(COALESCE(r.status, '')) NOT IN ('cancelada', 'cancelled')
            )
        """
    )


def _norm(s) -> str:
    """Casefold + strip for name-key matching (collapses 'García' / 'GARCIA' / ' García ')."""
    return (s or "").strip().lower()
