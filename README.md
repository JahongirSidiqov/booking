# Navbat — onlayn navbat va bron tizimi

Kichik xizmat biznesi (sartaroshxona, go'zallik saloni, stomatologiya, repetitor) uchun onlayn bron tizimi: mijoz xizmat va xodimni tanlaydi, bo'sh vaqtni ko'radi va bron qiladi; xodim o'z jadvalini boshqaradi; admin xizmatlar, xodimlar, ish vaqti va bronlarni boshqaradi.

Stack: Python 3.12 · Django 5.2 · Django REST Framework · PostgreSQL 16 · HTMX + Alpine.js + Tailwind CSS · Docker.

To'liq texnik topshiriq: [TASK.md](TASK.md).

## Tez boshlash (Docker)

```powershell
Copy-Item .env.example .env        # SECRET_KEY ni o'zgartiring
docker compose up --build          # db + web, http://localhost:8000
```

5432-port band bo'lsa, `.env` da `POSTGRES_PORT` va `DATABASE_URL` dagi portni o'zgartiring (masalan `5434`).

## Lokal ishga tushirish (Postgres Docker'da)

```powershell
docker compose up -d db
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements/dev.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Docker'siz: lokal PostgreSQL 14+ ham ishlaydi. Rolga `CREATEDB` huquqi kerak (pytest `test_navbat` bazasini o'zi yaratadi):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -p 5433 -c "CREATE ROLE navbat LOGIN PASSWORD 'navbat' CREATEDB;" -c "CREATE DATABASE navbat OWNER navbat;"
```

Keyin `.env` dagi `DATABASE_URL` portini lokal serverniki bilan almashtiring.

## Testlar va sifat

Testlar PostgreSQL'da ishlaydi (SQLite `EXCLUDE ... USING gist` ni qo'llamaydi), shuning uchun avval `docker compose up -d db`.

```powershell
pytest
ruff check .
ruff format --check .
pre-commit install                 # commit oldidan ruff avtomatik ishlaydi
```

## Loyiha tuzilishi

```
config/      settings (base/dev/test/prod), urls, wsgi/asgi
apps/        domen ilovalari (common, accounts, catalog, providers, scheduling, bookings, notifications, api, web)
tests/       pytest testlari
docs/        arxitektura, edge case'lar, AI jurnali, ADR'lar
docker/      Dockerfile, entrypoint.sh
```

## API

- Swagger UI: http://localhost:8000/api/docs/
- OpenAPI sxema: http://localhost:8000/api/schema/
- Bazaviy yo'l: `/api/v1/`, autentifikatsiya `Authorization: Bearer <access>` (`POST /api/v1/auth/token`).

## Hujjatlar

- [docs/decisions/](docs/decisions/) — arxitektura qarorlari (ADR)
- [docs/AI_USAGE.md](docs/AI_USAGE.md) — AI yordamida qilingan ishlar jurnali
