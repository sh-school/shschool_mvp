"""Scoped PostgreSQL RLS context helpers."""

from contextlib import contextmanager

from django.db import DatabaseError, connection


def _apply_rls_context(value: str) -> None:
    """Apply the tenant context to the current PostgreSQL connection."""
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_school_id', %s, false)",
            [value],
        )


def _current_rls_context() -> str:
    """Return the current tenant context without raising when it is unset."""
    if connection.vendor != "postgresql":
        return ""

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_school_id', true)")
        row = cursor.fetchone()

    return row[0] if row and row[0] else ""


@contextmanager
def rls_context(value: str):
    """Temporarily apply an RLS context and restore the previous value."""
    if connection.vendor != "postgresql":
        yield
        return

    try:
        previous = _current_rls_context()
        _apply_rls_context(value)
    except DatabaseError:
        connection.close()
        raise

    try:
        yield
    finally:
        try:
            _apply_rls_context(previous)
        except DatabaseError:
            connection.close()
            raise
