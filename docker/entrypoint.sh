#!/bin/sh
set -e

python manage.py migrate --noinput

case "$1" in
  gunicorn)
    python manage.py collectstatic --noinput
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --access-logfile -
    ;;
  runserver)
    exec python manage.py runserver 0.0.0.0:8000
    ;;
  *)
    exec "$@"
    ;;
esac
