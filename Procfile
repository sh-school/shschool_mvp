web: bash scripts/railway-release.sh && echo "🎯 Starting daphne (ASGI) on PORT=${PORT:-8080}" && exec daphne -b 0.0.0.0 -p ${PORT:-8080} --access-log - shschool.asgi:application
worker: celery -A shschool worker --loglevel=info --concurrency=2 --max-tasks-per-child=100
beat: celery -A shschool beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
