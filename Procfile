web: bash scripts/railway-release.sh && gunicorn shschool.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120 --access-logfile - --error-logfile -
worker: celery -A shschool worker --loglevel=info --concurrency=2 --max-tasks-per-child=100
beat: celery -A shschool beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
