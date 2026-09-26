# AI foydalanish jurnali

Loyiha Claude Code (Claude Opus) yordamida, TASK.md dagi bosqichlar bo'yicha qurilmoqda. Har bosqich uchun: prompt qisqacha → nima generatsiya bo'ldi → qanday tekshirildi → nima o'zgartirildi → AI xatolari.

## Umumiy yondashuv

- Vosita: Claude Code (Claude Opus 5.5), VS Code ichida, Windows + PowerShell.
- Har bosqich TASK.md 14-bo'limi bo'yicha alohida so'raladi; AI bosqich oxirida to'xtaydi, men natijani ko'rib "davom et" deyman.
- Tekshirish usullari: `pytest`, `ruff check` / `ruff format --check`, `manage.py check`, pre-commit hook'lari, kodni o'qib chiqish.

## 0-bosqich — Skeleton

**Prompt (qisqacha):** TASK.md ni o'qish, CLAUDE.md va shu faylni yaratish, 0-bosqichni qurish (TASK.md 16-bo'limdagi birinchi xabar).

**Generatsiya qilindi:**
- `CLAUDE.md` — TASK.md 0, 2, 3.1, 3.2-bo'limlaridan qisqa qo'llanma.
- `config/settings/{base,dev,test,prod}.py` (django-environ, `DATABASE_URL`, UTC saqlash, prod `SECURE_*`), `manage.py`, `urls.py`, wsgi/asgi, `apps/common` app config.
- `requirements/{base,dev,prod}.txt`, `pyproject.toml` (ruff + pytest), `.pre-commit-config.yaml`, `.gitignore`, `.gitattributes`, `.env.example`.
- `docker/Dockerfile` (multi-stage, non-root), `docker/entrypoint.sh`, `docker-compose.yml` (postgres:16 + healthcheck, web), `.github/workflows/ci.yml` (lint → pytest Postgres service bilan → docker build).
- `tests/test_smoke.py`, README skeleti, ADR-001, ADR-002.

**Qanday tekshirildi:**
- `ruff check .`, `ruff format --check .` — toza; `python manage.py check` — xatosiz.
- `pre-commit run --all-files` — barcha hook'lar o'tdi.
- `pytest`: 3/3 o'tdi — lokal PostgreSQL 18 (5433-port) ustida, `btree_gist` 1.8 mavjud.
- `docker compose up` hali tekshirilmagan: mashinada Docker yo'q. Compose/Dockerfile birinchi marta CI'da (GitHub remote qo'shilgach) yoki Docker o'rnatilganda tekshiriladi.

**AI xatolari / muhitga moslashtirish:**
- ruff 0.16 Markdown ichidagi Python kod bloklarini ham formatlaydi — `TASK.md` "formatlanmagan" deb chiqdi. `*.md` ruff'dan chiqarildi.
- PowerShell 5.1 `Set-Content -Encoding utf8` `.env` ga BOM yozdi, django-environ birinchi qatorni o'qiy olmadi. BOM olib tashlandi; keyingi fayllar LF/BOM'siz yoziladi.
- Mashinada Docker o'rnatilmagan, 5432 va 5433 portlar lokal PostgreSQL bilan band. Compose'da host port `POSTGRES_PORT` o'zgaruvchisiga chiqarildi, lokal `.env` da 5434.
- `trailing-whitespace` hook'i TASK.md dagi bitta ortiqcha bo'shliqni olib tashladi (mazmun o'zgarmadi).
- Lokal Python 3.14, Docker image va CI 3.12 — ikkalasida ham Django 5.2 ishlaydi.
- Docker o'rniga lokal PostgreSQL 18 tanlandi (mening qarorim). `postgres` paroli esdan chiqqan edi — AI `pg_hba.conf` ni vaqtincha `trust` qilib parolni tiklash skriptini berdi, men uni admin PowerShell'da ishlatdim; keyin konfiguratsiya qayta `scram-sha-256` ga qaytganini AI tekshirdi.
- DB ishlamayotganda `pytest` 2 daqiqadan ko'p osilib qoldi. `connect_timeout=5` qo'shildi — endi ~30 soniyada xato bilan tugaydi.

## 1-bosqich — Accounts + auth

## 2-bosqich — Catalog + providers

## 3-bosqich — Scheduling

## 4-bosqich — Slot engine

## 5-bosqich — Booking create + concurrency

## 6-bosqich — State machine

## 7-bosqich — API polish

## 8-bosqich — UI (mijoz)

## 9-bosqich — UI (dashboard)

## 10-bosqich — Notifications

## 11-bosqich — Ops

## 12-bosqich — Hujjat va yakun

## Nimani o'zim yozdim / o'zgartirdim
