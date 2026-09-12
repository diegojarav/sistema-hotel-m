"""
Fresh-schema default parity (found by the 2026-09-12 VM rebuild).

Migrations add NOT NULL columns with SQL defaults (`ALTER TABLE ... NOT NULL
DEFAULT 0`), but SQLAlchemy's `default=` is Python-side only — a column
declared `nullable=False, default=0` WITHOUT `server_default` produces a bare
`NOT NULL` on fresh `init_db()`. Raw-INSERT callers that omit the column
(seed_monges.py) then crash with IntegrityError — but only on from-scratch
environments, so the drift stays invisible until a disaster-recovery rebuild.

Rule locked in here: every NOT NULL column with a scalar Python default MUST
also declare a matching `server_default`.
"""
import sqlite3

from sqlalchemy import create_engine

from database import Base


def test_not_null_python_defaults_have_server_defaults():
    """Schema-wide parity scan — new columns can't reintroduce the drift."""
    offenders = [
        f"{table.name}.{col.name}"
        for table in Base.metadata.tables.values()
        for col in table.columns
        if not col.nullable
        and col.default is not None
        and getattr(col.default, "is_scalar", False)
        and col.server_default is None
        and not col.primary_key
    ]
    assert not offenders, (
        "NOT NULL columns with Python-side default but no server_default "
        f"(fresh init_db() schemas will reject raw INSERTs): {offenders}"
    )


def test_fresh_schema_accepts_raw_insert_omitting_defaulted_columns(tmp_path):
    """The exact seed_monges failure mode: raw sqlite3 INSERT into a fresh
    schema providing only the truly-required columns."""
    db_file = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    engine.dispose()

    props = Base.metadata.tables["properties"]
    # Columns a raw inserter genuinely must provide: NOT NULL, no SQL
    # default, no PK autoincrement. Everything else must be omittable.
    required = [
        c for c in props.columns
        if not c.nullable and c.server_default is None and c.default is None
    ]
    dummy = {
        c.name: ("test-prop" if c.primary_key else
                 "x" if str(c.type) in ("VARCHAR", "TEXT") else 1)
        for c in required
    }
    dummy.setdefault("id", "test-prop")

    conn = sqlite3.connect(db_file)
    cols = ", ".join(dummy)
    ph = ", ".join("?" for _ in dummy)
    conn.execute(f"INSERT INTO properties ({cols}) VALUES ({ph})", tuple(dummy.values()))
    conn.commit()

    row = conn.execute(
        "SELECT early_checkin_surcharge, late_checkout_surcharge, "
        "cleaning_buffer_minutes FROM properties WHERE id = ?",
        (dummy["id"],),
    ).fetchone()
    conn.close()
    assert row == (0, 0, 30)
