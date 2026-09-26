# Navbat — onlayn navbat va bron tizimi

Kichik xizmat biznesi (sartaroshxona, go'zallik saloni, klinika, repetitor) uchun onlayn bron: mijoz xizmat, xodim va bo'sh vaqtni tanlab bron qiladi; xodim o'z jadvali va bronlarini boshqaradi; admin xizmatlar, xodimlar, ish vaqti, bronlar va sozlamalarni boshqaradi. Bitta vaqtga ikki bron **ma'lumotlar bazasi darajasida** taqiqlangan.

**Stack:** Python 3.12 · Django 5.2 · Django REST Framework · PostgreSQL 16 · HTMX + Alpine.js + Tailwind CSS v4 · Docker · GitHub Actions

| Mijoz (telefon) | | |
|---|---|---|
| ![Xizmatlar](docs/screenshots/mobile-services.png) | ![Vaqt tanlash](docs/screenshots/mobile-time-picker.png) | ![Bronlarim](docs/screenshots/mobile-my-bookings.png) |

| Boshqaruv paneli | |
|---|---|
| ![Kun ko'rinishi](docs/screenshots/desktop-dashboard-today.png) | ![Bronlar jadvali](docs/screenshots/desktop-dashboard-bookings.png) |
| ![Bron tafsiloti](docs/screenshots/desktop-booking-detail.png) | ![Ish vaqti muharriri](docs/screenshots/desktop-availability.png) |

## Demo

Demo URL deploydan keyin shu yerga qo'shiladi ([docs/DEPLOY.md](docs/DEPLOY.md)). Lokal demo: `python manage.py seed_demo` — 5 xizmat, 3 xodim, haftalik jadvallar, 1 dam olish, barcha statusdagi ~25 bron (hammasi haqiqiy service qatlami orqali yaratiladi).

| Rol | Email | Parol | Nima ko'radi |
|---|---|---|---|
| Admin | `admin@navbat.uz` | `Navbat-Demo-2026` | `/dashboard/` — hammasi; `/django-admin/` |
| Xodim (Sardor) | `sardor@navbat.uz` | `Navbat-Demo-2026` | o'z bronlari va ish vaqti |
| Mijoz | `mijoz@navbat.uz` | `Navbat-Demo-2026` | bron qilish, "Bronlarim" |

Parol: `DEMO_PASSWORD` yoki `seed_demo --password …`. Qayta yaratish: `python manage.py flush --no-input; python manage.py seed_demo`.

## Imkoniyatlar

- **Bron oqimi:** xodim → sana chizig'i (har kunda bo'sh slotlar soni) → vaqt chiplari (Ertalab / Kunduzi / Kechqurun, HTMX) → tasdiq → natija. Band bo'lib qolgan vaqt — do'stona xabar va yangilangan slotlar; ikki marta bosish — bitta bron.
- **To'g'rilik:** provider qatoriga lock + PostgreSQL `EXCLUDE` constraint (10 parallel so'rov → 1 g'olib), idempotency kaliti, holatlar mashinasi (`pending → confirmed → completed`, `cancelled`), bekor qilish muddati, o'zgarmas status tarixi.
- **Vaqt:** DB'da UTC, ish vaqti xodimning mahalliy vaqtida (DST'da ham to'g'ri), mijoz o'z zonasida ko'radi, API'da offset majburiy; qurilma zonasi boshqacha bo'lsa bir bosishda o'tish (anonim foydalanuvchida ham).
- **Kalendar:** har bron `.ics` fayl sifatida (Google/Apple/Outlook); bekor qilinsa `STATUS:CANCELLED`.
- **Boshqaruv paneli:** xodimlar ustunlari bilan kun ko'rinishi va KPI, bronlar jadvali (filtr, qidiruv, sahifalash), tasdiqlash / bajarildi / sababli bekor qilish, xizmatlar, xodimlar, haftalik ish vaqti va dam olish, sozlamalar. Jadval o'zgarishi faol bron bilan to'qnashsa — ro'yxat bilan rad etiladi.
- **API:** REST (JWT, refresh rotation + token oilasi), yagona xato formati (RFC 9457), filtrlar, sahifalash, throttle, Swagger.
- **Email:** yaratildi / tasdiqlandi / bekor qilindi — faqat commit'dan keyin; pochta xatosi bronni buzmaydi.
- **Ops:** `/healthz`, muddati o'tgan `pending` bronlarni bekor qiluvchi scheduler, prod Docker Compose + Caddy (HTTPS), Render blueprint.

## Tez boshlash (Docker)

```powershell
Copy-Item .env.example .env        # SECRET_KEY ni o'zgartiring
docker compose up --build          # db + web → http://localhost:8000
docker compose exec web python manage.py seed_demo
```

5432-port band bo'lsa, `.env` da `POSTGRES_PORT` va `DATABASE_URL` portini o'zgartiring (masalan `5434`).

## Lokal ishga tushirish (Windows / PowerShell)

```powershell
docker compose up -d db
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements/dev.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Docker'siz lokal PostgreSQL 14+ ham ishlaydi (rolga `CREATEDB` kerak — pytest test bazasini o'zi yaratadi):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -p 5433 -c "CREATE ROLE navbat LOGIN PASSWORD 'navbat' CREATEDB;" -c "CREATE DATABASE navbat OWNER navbat;"
```

Keyin `.env` dagi `DATABASE_URL` portini lokal serverniki bilan almashtiring.

## Sozlamalar (`.env`)

| O'zgaruvchi | Izoh |
|---|---|
| `SECRET_KEY` | majburiy |
| `DATABASE_URL` | `postgres://navbat:navbat@localhost:5432/navbat` |
| `ALLOWED_HOSTS`, `SITE_URL` | xatlardagi havolalar uchun `SITE_URL` |
| `DEFAULT_TZ` | biznesning boshlang'ich zonasi (`Asia/Tashkent`) |
| `EMAIL_BACKEND`, `EMAIL_*` | dev'da `console` — xatlar terminalga chiqadi |
| `DEMO_PASSWORD` | `seed_demo` akkauntlari paroli |

Production ro'yxati: [`.env.prod.example`](.env.prod.example).

## Testlar va sifat

Testlar PostgreSQL'da ishlaydi (SQLite `EXCLUDE … USING gist` ni bilmaydi).

```powershell
pytest                              # ~570 test, jumladan 10 thread'li concurrency testi
pytest --cov                        # qamrov ~98%
pytest -k edge_24 -v                # TASK 8-bo'limdagi istalgan holat
ruff check .; ruff format --check .
pre-commit install                  # commit oldidan ruff va boshqa tekshiruvlar
```

Brauzer testlari (360px / 1440px da gorizontal scroll yo'qligi, faqat klaviatura bilan bron, dashboard dialoglari):

```powershell
pip install -r requirements/e2e.txt
python -m playwright install chromium
pytest tests/e2e
```

CI (`.github/workflows/ci.yml`): ruff → CSS eskirmaganligi → pytest (Postgres 16) → `check --deploy` → toza bazada `seed_demo` → Docker build → prod compose'ni ko'tarib smoke test.

## CSS

Tailwind v4 standalone CLI (Node.js kerak emas). Manba — `assets/css/`, natija — `static/css/app.css` (repoda saqlanadi; CI shablonlarga mosligini tekshiradi, Docker image qaytadan yig'adi):

```powershell
.\scripts\build-css.ps1
```

## API

- Swagger UI: http://localhost:8000/api/docs/ · OpenAPI: http://localhost:8000/api/schema/
- Bazaviy yo'l `/api/v1/`, autentifikatsiya `Authorization: Bearer <access>` (`POST /api/v1/auth/token`).
- Xato formati hamma joyda bir xil: `{"type", "title", "status", "code", "detail", "errors"?}`.

## Loyiha tuzilishi

```
config/        settings (base/dev/test/prod), urls, wsgi/asgi
apps/
  common/      BaseModel, DomainError, xato handler'i, /healthz, seed_demo
  accounts/    User (email login, rol, zona), JWT token oilasi
  catalog/     Service
  providers/   Provider, ProviderService
  scheduling/  ish vaqti, dam olish, sozlamalar, slot engine
  bookings/    Booking, status tarixi, state machine, services, expire_stale_bookings
  notifications/  email yuboruvchilar
  api/         REST API v1, OpenAPI
  web/         mijoz sahifalari va boshqaruv paneli
templates/     base, komponentlar, sahifalar, email'lar
assets/css/    Tailwind manbasi         static/   css, js (htmx, alpine), shriftlar
tests/         unit, api, web, concurrency, notifications, e2e
docs/          arxitektura, edge case'lar, deploy, AI jurnali, ADR'lar
docker/        Dockerfile, entrypoint.sh, Caddyfile
```

## Hujjatlar

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — qatlamlar, bron oqimi, DB, slot engine, state machine, vaqt zonalari, trade-off'lar
- [docs/EDGE_CASES.md](docs/EDGE_CASES.md) — 38 ta holat, natija va testlari
- [docs/decisions/](docs/decisions/) — ADR-001…009
- [docs/DEPLOY.md](docs/DEPLOY.md) — Render, Railway, VPS
- [docs/INTERVIEW_NOTES.md](docs/INTERVIEW_NOTES.md) — asosiy qarorlar qisqacha
- [docs/AI_USAGE.md](docs/AI_USAGE.md) — AI yordamida qilingan ishlar jurnali
- [TASK.md](TASK.md) — texnik topshiriq

## Litsenziya

[MIT](LICENSE)
