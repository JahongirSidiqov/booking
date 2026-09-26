#!/bin/sh
set -e

case "$1" in
  gunicorn)
    # Only the web process migrates, so the scheduler container never races it.
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    exec gunicorn config.wsgi:application \
      --bind "0.0.0.0:${PORT:-8000}" \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout "${GUNICORN_TIMEOUT:-30}" \
      --access-logfile - \
      --forwarded-allow-ips "*"
    ;;
  runserver)
    python manage.py migrate --noinput
    exec python manage.py runserver "0.0.0.0:${PORT:-8000}"
    ;;
  scheduler)
    # TASK 5.3: a plain loop instead of cron/django-crontab — one process, no extra deps.
    # `sleep & wait` keeps the shell responsive to SIGTERM on `docker compose stop`.
    trap 'exit 0' TERM INT
    echo "scheduler: expire_stale_bookings every ${EXPIRE_INTERVAL_SECONDS:-300}s"
    while true; do
      python manage.py expire_stale_bookings || echo "scheduler: run failed, retrying next tick"
      sleep "${EXPIRE_INTERVAL_SECONDS:-300}" &
      wait $!
    done
    ;;
  *)
    exec "$@"
    ;;
esac
