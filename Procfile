release: python manage.py migrate && python manage.py createsuperuser --noinput || true
web: gunicorn core.wsgi:application --bind 0.0.0.0:$PORT