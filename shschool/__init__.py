# shschool/__init__.py
# تحميل Celery عند بدء Django — ضروري لـ @shared_task
from .celery import app as celery_app

__all__ = ("celery_app",)
