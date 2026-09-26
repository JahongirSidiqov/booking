# CLAUDE.md — Navbat (Appointment Booking System)

To'liq texnik topshiriq: [TASK.md](TASK.md). Bu fayl — qisqa ish qo'llanmasi; ziddiyat bo'lsa TASK.md ustun.

## Loyiha
- **Nomi:** Navbat — kichik xizmat biznesi (sartaroshxona, salon, klinika) uchun onlayn navbat/bron tizimi.
- **Demo:** "Navbat Barbershop" — 3 xodim, 5 xizmat.
- **Rollar:** `customer`, `provider`, `admin`.
- **Ish tartibi:** TASK.md 14-bo'limdagi bosqichlar (0–12), keyin bonuslar. Har bosqichdan keyin to'xtab hisobot beriladi, foydalanuvchi "davom et" demaguncha keyingisi boshlanmaydi.

## Stack
- Python 3.12 (Docker image), Django 5.2, Django REST Framework, drf-spectacular
- PostgreSQL 16 (Docker) — majburiy, testlar ham Postgres'da (`btree_gist` + `ExclusionConstraint`)
- Auth: simplejwt (API: access 15 daq, refresh 7 kun, rotation + blacklist) + Django session (UI)
- UI: Django templates + HTMX + Alpine.js + Tailwind CSS, Lucide ikonkalar, Inter shrifti
- Email: Django EmailBackend + `transaction.on_commit` (Celery yo'q)
- Test: pytest, pytest-django, factory_boy, freezegun
- Sifat: ruff (lint + format), pre-commit
- Deploy: Docker multi-stage, docker compose, Gunicorn + WhiteNoise, GitHub Actions
- Config: django-environ, `.env.example`

## Papka tuzilishi (TASK.md 3.2)
```
config/                 settings/{base,dev,test,prod}.py, urls.py, asgi.py, wsgi.py
apps/
  common/               DomainError, exception handler, BaseModel(uuid, created, updated), utils/time.py
  accounts/             User (email login, role), JWT views, register
  catalog/              Service
  providers/            Provider, ProviderService
  scheduling/           AvailabilityRule, TimeOff, BusinessSettings, slot_engine.py
  bookings/             Booking, BookingStatusHistory, services.py, selectors.py, state_machine.py
  notifications/        email templates, senders (on_commit)
  api/                  v1/ routers, serializers, permissions, throttles, openapi
  web/                  HTML views, forms, templates/, static/
templates/              base.html, partials/
static/                 css (tailwind build), js (htmx, alpine)
tests/                  unit/, api/, web/, concurrency/, factories.py, conftest.py
docs/                   ARCHITECTURE.md, EDGE_CASES.md, AI_USAGE.md, decisions/ADR-*.md
docker/                 Dockerfile, entrypoint.sh
requirements/           base.txt, dev.txt, prod.txt
docker-compose.yml, docker-compose.prod.yml, .github/workflows/ci.yml, .env.example, pyproject.toml, manage.py
```

## Arxitektura qoidalari (TASK.md 3.1)
```
api/ (DRF) , web/ (views+forms)   → faqat shakl validatsiyasi, input → service → output
services/                          → biznes qoidalari, transaction, lock, state machine — YAGONA yozish nuqtasi
selectors/                         → o'qish so'rovlari, slot engine (pure funksiyalar)
models/                            → maydonlar, constraint'lar, index'lar (mantiqsiz)
```
- View'da biznes mantiq yo'q.
- **`Booking.status` faqat `apps/bookings/services.py` da o'zgaradi.** Boshqa joyda `booking.status = ...` taqiqlangan — `tests/test_architecture.py` grep bilan tekshiradi.
- Model `save()` ichida cross-model logika yo'q.
- Slot engine — pure funksiyalar: DB'siz, `now` parametr sifatida keladi.
- Domen xatolari: `common.exceptions.DomainError(code, message, status)`; API ham, UI ham uni bir xil formatga (RFC 9457 uslubi, TASK.md 6.2) aylantiradi.
- Barcha vaqtlar DB va service qatlamida aware UTC. API'da `start_at` offset bilan majburiy.
- Double booking: `select_for_update(Provider)` + `ExclusionConstraint` (`[)` range) — ikkalasi ham.
- Service/Provider hech qachon hard delete emas — `is_active=False`.

## Ish qoidalari (TASK.md 0-bo'lim)
1. Bosqichma-bosqich: kod → test → hujjat → commit. Test o'tmasa keyingi bosqich yo'q.
2. Bosqich boshida 3–6 qatorli reja; oxirida hisobot (nima qilindi, qarorlar, qo'lda nimani tekshirish kerak).
3. Git: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`), bitta commit = bitta mantiqiy o'zgarish, bosqichda 2–5 commit.
4. Muhim qaror → `docs/decisions/ADR-0NN-nomi.md` (Kontekst → Variantlar → Tanlov → Sabab → Oqibatlar).
5. `docs/AI_USAGE.md` har bosqichda yangilanadi — rostini yozish.
6. Izohlar faqat "nima uchun" (slot generatsiya, lock, state machine, timezone). "Nima qilyapti" izohi yozilmaydi.
7. Placeholder, TODO, mock data relizga kirmaydi.
8. Muhit: Windows + PowerShell. Buyruqlar PowerShell uchun.
9. UI bosqichidan oldin `frontend-uiux-skill` va TASK.md 10-bo'lim o'qiladi.
10. Bilmagan narsani o'ylab topma — `pip show` / docs tekshir yoki so'ra.

## Konvensiyalar
- O'zbekcha matnda `ʻ` (U+02BB: oʻ, gʻ) va `ʼ` (U+02BC: maʼlumot) ishlatiladi; ruff RUF001-003 shu sabab o'chirilgan.
- API URL'lari oxirida `/` yo'q (`/api/v1/auth/token`).
- API xatolari faqat `DomainError` yoki DRF exception orqali; javob shakli `apps/common/exceptions.py` da.
- Bash heredoc'da `'` + `ʻ` aralash matn buziladi — Python fayllarni Write vositasi bilan yozish.
- Skript orqali matn almashtirishda `\b`, `\a` kabi ketma-ketliklar boshqaruv belgisiga aylanadi — `tests/test_architecture.py` buni ushlaydi.
- Tailwind CLI `-o` OneDrive papkasida EEXIST beradi (Bun bug) — CSS stdout orqali yoziladi (`scripts/build-css.ps1`).
- Tailwind faqat `templates/` va `apps/` ni skanerlaydi (`source(none)`) — hujjat o'zgarishi CSS'ga ta'sir qilmaydi.
- Shablon yoki `assets/css` o'zgarsa `static/css/app.css` qayta yig'ilib commit qilinadi (CI tekshiradi).
- Bu mashinada Docker yo'q: dev/test bazasi lokal PostgreSQL 18, port 5433 (`.env` dagi `DATABASE_URL`).

## PowerShell buyruqlari
```powershell
# Muhit
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements/dev.txt
Copy-Item .env.example .env

# DB (Docker)
docker compose up -d db
docker compose up            # db + web

# Django
python manage.py migrate
python manage.py seed_demo
python manage.py runserver

# CSS (Tailwind v4 standalone CLI, Node'siz)
.\scripts\build-css.ps1

# Sifat va testlar
ruff check .
ruff format --check .
pytest
pytest tests/concurrency -v
pytest tests/e2e              # Playwright + Chromium kerak (requirements/e2e.txt)
```
