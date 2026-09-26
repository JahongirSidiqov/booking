# Deploy

Navbat uchta jarayondan iborat: **web** (gunicorn), **scheduler** (har 5 daqiqada `expire_stale_bookings`) va **PostgreSQL 16** (`btree_gist` kengaytmasi bilan — migratsiya uni o'zi yaratadi). Bitta Docker image ikkala jarayon uchun: `docker/entrypoint.sh gunicorn | scheduler`.

## Muhit o'zgaruvchilari

To'liq ro'yxat: [`.env.prod.example`](../.env.prod.example). Majburiylari:

| O'zgaruvchi | Izoh |
|---|---|
| `SECRET_KEY` | uzun tasodifiy qator (`python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DATABASE_URL` | `postgres://user:pass@host:5432/db` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` | domen. Render/Railway'da avtomatik: `RENDER_EXTERNAL_HOSTNAME` / `RAILWAY_PUBLIC_DOMAIN` qo'shiladi |
| `NUM_PROXIES` | platforma yoki Caddy orqasida `1` — throttle haqiqiy mijoz IP'si bo'yicha ishlaydi |
| `EMAIL_*` | SMTP; demo uchun `console` backend yetarli (xatlar logga yoziladi) |

Birinchi ishga tushishda web jarayoni `migrate` va `collectstatic` ni o'zi bajaradi. Demo ma'lumot uchun bir marta: `python manage.py seed_demo` (faqat bo'sh bazada; loginlar README'da).

## 1. Render (eng tez demo URL)

1. Repo GitHub'da bo'lsin.
2. Render → **New → Blueprint** → repo. [`render.yaml`](../render.yaml) Postgres 16, `navbat` web servisi va `navbat-scheduler` worker'ini yaratadi. `SECRET_KEY` avtomatik generatsiya bo'ladi, `DEMO_PASSWORD` ni o'zingiz kiritasiz.
3. Deploy tugagach: Render → navbat → **Shell** → `python manage.py seed_demo`.
4. Tekshirish: `https://<servis>.onrender.com/healthz` → `{"status": "ok", "database": "ok"}`.

Eslatmalar:
- Render'da worker bepul tarifda yo'q. Pul to'lanmasa, worker'ni `render.yaml` dan olib tashlang va `python manage.py expire_stale_bookings` ni Render Cron Job yoki tashqi scheduler orqali har 5 daqiqada chaqiring — busiz o'tib ketgan `pending` bronlar avtomatik bekor bo'lmaydi (boshqa hech narsa buzilmaydi).
- Bepul web servis uyquga ketadi; birinchi so'rov ~30–60 soniya olishi mumkin.
- Render Postgres `btree_gist` ni qo'llaydi; agar migratsiya `CREATE EXTENSION` da yiqilsa, bazaga `CREATE EXTENSION btree_gist;` ni qo'lda bajarib, qayta deploy qiling.

## 2. Railway

1. New Project → **Deploy from GitHub repo** → Dockerfile yo'li: `docker/Dockerfile`.
2. **Add → Database → PostgreSQL**; web servisga `DATABASE_URL=${{Postgres.DATABASE_URL}}` qo'shing.
3. O'zgaruvchilar: `DJANGO_SETTINGS_MODULE=config.settings.prod`, `SECRET_KEY`, `NUM_PROXIES=1`, `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`.
4. Settings → Networking → **Generate Domain**. Healthcheck path: `/healthz`.
5. Scheduler: shu repo'dan ikkinchi servis, **Custom Start Command** `/app/docker/entrypoint.sh scheduler`, xuddi shu o'zgaruvchilar.
6. Web servis shell'ida: `python manage.py seed_demo`.

## 3. VPS (Docker Compose + Caddy, avtomatik HTTPS)

```bash
git clone <repo> navbat && cd navbat
cp .env.prod.example .env.prod          # SECRET_KEY, POSTGRES_PASSWORD, domen, SMTP
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile caddy up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py seed_demo
```

- `DOMAIN` ning DNS A yozuvi serverga qarasin; Caddy Let's Encrypt sertifikatini o'zi oladi.
- Yangilash: `git pull && docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
- Zaxira: `docker compose -f docker-compose.prod.yml exec db pg_dump -U navbat navbat > backup.sql`.
- Loglar: `docker compose -f docker-compose.prod.yml logs -f web scheduler`.

Bu stek CI'dagi `compose-smoke` job'ida har push'da to'liq ishga tushirib tekshiriladi (build, migrate, `/healthz`, HTTPS redirect, statik fayllar, `seed_demo`, scheduler logi).

## Deploydan keyin tekshirish

- [ ] `/healthz` → 200
- [ ] `http://` → `https://` ga 301
- [ ] `/api/docs/` ochiladi
- [ ] `admin@navbat.uz` bilan kirish → `/dashboard/`
- [ ] mijoz sifatida bron → email logda (yoki pochtada)
- [ ] scheduler logida `expired: N`
