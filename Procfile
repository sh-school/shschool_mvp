web: bash scripts/railway-release.sh && echo "🎯 Starting gunicorn on PORT=${PORT:-8080}" && exec gunicorn shschool.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers 3 --timeout 120 --access-logfile - --error-logfile - --log-level info --capture-output
worker: celery -A shschool worker --loglevel=info --concurrency=2 --max-tasks-per-child=100
beat: celery -A shschool beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
