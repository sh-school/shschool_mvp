"""Security-focused Celery task base classes.

[SEC-08] `app.current_school_id` is no longer the tenant authority. Since
migration 0037 every `school_isolation` policy resolves the tenant through
`public.app_rls_school()`, which reads the role -> school mapping keyed by
`session_user`. The session variable these helpers set is diagnostic context,
not an isolation mechanism.

That has a consequence worth stating plainly: a worker connects as exactly one
database role, so it can only ever reach one school. Entering the scope of a
different school does not widen access — measured in production, a foreign
scope returned the worker's own rows unchanged — but it also does not fail.
Reads silently return nothing and writes are rejected by WITH CHECK, so there
is no leak; what is missing is a signal. A task that believes it is processing
school B would report success having processed nothing.

`school_rls_scope` therefore *asserts* the tenant rather than establishing it.
"""

from contextlib import contextmanager
from inspect import signature
from uuid import UUID

from celery import Task
from django.db import connection

from core.rls import reset_rls_context, rls_context


def canonical_school_id(raw_school_id):
    """Return one canonical school UUID or fail closed."""
    if raw_school_id in (None, ""):
        raise ValueError("school_id is required")

    try:
        return str(UUID(str(raw_school_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("school_id must be a valid school UUID") from exc


def rls_is_enforced_for_current_role():
    """
    Is the current database role actually subject to row-level security?

    Superuser and BYPASSRLS roles are exempt from every policy, so the tenant
    assertion below would compare against an identity the database never
    applies. Migrations, management commands and the CI test database all run
    as such a role; the worker does not.
    """
    if connection.vendor != "postgresql":
        return False

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT coalesce(bool_or(rolsuper OR rolbypassrls), false) "
            "FROM pg_roles WHERE rolname = current_user"
        )
        row = cursor.fetchone()

    return not (row and row[0])


def db_role_tenant():
    """Return the school bound to the connecting role, or None when unbound."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT public.app_rls_school()")
        row = cursor.fetchone()

    return str(row[0]) if row and row[0] else None


@contextmanager
def school_rls_scope(school_id):
    """
    Assert that this task's school matches the tenant bound to the DB role.

    [SEC-08] This does not establish isolation — PostgreSQL already does, from
    `session_user`. It converts the one failure mode that isolation leaves
    silent into an observable one: asking a worker bound to school A to process
    school B used to return zero rows and report success, which is
    indistinguishable from "school B had nothing to do".

    Fail-closed on a missing binding as well: an enforced role with no mapping
    row resolves every policy against NULL, so the task would process nothing
    at all.
    """
    canonical = canonical_school_id(school_id)

    if rls_is_enforced_for_current_role():
        bound = db_role_tenant()

        if bound is None:
            raise ValueError(
                "Celery tenant binding missing: the connecting database role "
                "has no row in app_rls_role_school, so every school-scoped "
                "policy would evaluate against NULL"
            )

        if bound != canonical:
            raise ValueError(
                "Celery tenant mismatch: task requested a school the "
                "connecting database role is not bound to; this worker can "
                "only reach its own tenant"
            )

    with rls_context(canonical):
        yield canonical


class RLSIsolatedTask(Task):
    """Prevent PostgreSQL tenant context from leaking across Celery tasks."""

    abstract = True

    def __call__(self, *args, **kwargs):
        # Eager mode runs inside the HTTP/request process.
        if getattr(self.request, "is_eager", False):
            with rls_context(""):
                return self._execute(*args, **kwargs)

        # Real workers may reuse one PostgreSQL connection.
        reset_rls_context()
        try:
            return self._execute(*args, **kwargs)
        finally:
            reset_rls_context()

    def _execute(self, *args, **kwargs):
        return self.run(*args, **kwargs)


class TenantRLSTask(RLSIsolatedTask):
    """Run one tenant-bound task inside exactly one school scope."""

    abstract = True

    def _resolve_school_id(self, args, kwargs):
        try:
            bound = signature(self.run).bind_partial(
                *args,
                **kwargs,
            )
        except TypeError as exc:
            raise ValueError("Unable to bind tenant task arguments") from exc

        bound.apply_defaults()

        raw_school_id = bound.arguments.get("school_id")

        if raw_school_id in (None, ""):
            raise ValueError("Tenant Celery task requires school_id")

        return canonical_school_id(raw_school_id)

    def _execute(self, *args, **kwargs):
        school_id = self._resolve_school_id(args, kwargs)

        with school_rls_scope(school_id):
            return self.run(*args, **kwargs)
