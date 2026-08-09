"""Security-focused Celery task base classes."""

from contextlib import contextmanager
from inspect import signature
from uuid import UUID

from celery import Task

from core.rls import reset_rls_context, rls_context


def canonical_school_id(raw_school_id):
    """Return one canonical school UUID or fail closed."""
    if raw_school_id in (None, ""):
        raise ValueError("school_id is required")

    try:
        return str(UUID(str(raw_school_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("school_id must be a valid school UUID") from exc


@contextmanager
def school_rls_scope(school_id):
    """Enter exactly one school RLS scope; wildcard is impossible."""
    canonical = canonical_school_id(school_id)

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
