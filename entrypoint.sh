#!/bin/sh

echo "🔄 Применяем миграции..."
uv run python manage.py makemigrations --noinput
uv run python manage.py migrate --noinput

echo "🧹 Собираем статику..."
uv run python manage.py collectstatic --noinput


echo "👤 Создаем суперюзера, если его нет..."
uv run python manage.py shell -c "
from django.contrib.auth import get_user_model;
from django.conf import settings
User = get_user_model();
if not User.objects.filter(username=settings.SUPERUSER_NAME).exists() or not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(
            email=settings.SUPERUSER_EMAIL,
            username=settings.SUPERUSER_NAME,
            password=settings.SUPERUSER_PASSWORD,
            is_active=True
    );
"

echo "Запускаем сервер"
exec uv run gunicorn config.wsgi:application --workers 2 --bind 0.0.0.0:8000