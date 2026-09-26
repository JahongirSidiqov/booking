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

**Prompt (qisqacha):** "davom et" — 14-bo'lim, 1-bosqich (custom user, JWT, auth testlari).

**Generatsiya qilindi:**
- `apps/common`: `BaseModel` (UUID pk, created/updated), `DomainError`, RFC 9457 uslubidagi `problem_exception_handler`, `utils/time.py` (IANA tekshiruvi).
- `apps/accounts`: `User` (email login, role, phone `+998…`, timezone), `UserManager` (email lowercase, case-insensitive login), DB CHECK'lar (email lowercase, role), admin formalari, `services.py` (register, profil, token oilasi).
- `apps/api/v1`: `auth/register`, `auth/token`, `auth/token/refresh`, `auth/logout`, `me` (GET/PATCH); throttle'lar (anon 60, user 120, login 10/min IP bo'yicha).
- Testlar: `tests/api/test_auth.py` (31), `tests/unit/test_user_model.py`, `tests/unit/test_time_utils.py`, `tests/test_admin.py`, `factories.py`, `conftest.py`.

**Qanday tekshirildi:**
- `pytest`: 50/50 yashil (lokal PostgreSQL 18). Qamrov: jami 90%, `accounts/services.py` 95%.
- `ruff check`, `ruff format --check`, `makemigrations --check` — toza; dev bazaga `migrate` o'tdi.
- simplejwt manba kodi o'qildi (`serializers.py`, `tokens.py`, `token_blacklist/models.py`): rotation va blacklist bor, lekin "token oilasi" yo'q.

**Qarorlar:**
- **Refresh token oilasi (TASK #30).** simplejwt eski refresh qayta ishlatilganda faqat shu so'rovni 401 qiladi. Login'da `fam` claim qo'shiladi (rotation'da saqlanadi); allaqachon blacklist qilingan, imzosi to'g'ri va muddati o'tmagan refresh kelsa — shu oiladagi barcha tirik tokenlar blacklist qilinadi. Boshqa qurilmadagi sessiya (boshqa oila) tegilmaydi — alohida test bor.
- **Xato formati 7-bosqichdan oldinga surildi.** 14-bo'limda `problem-details error handler` 7-bosqichda, lekin 1-bosqich testlari 422/401 kodlarini tekshiradi. Keyin barcha testlarni qayta yozmaslik uchun handler hozir qurildi; 7-bosqichda `IntegrityError(exclusion)` va qolgan kodlar qo'shiladi.
- Login xatosi 401 (DRF autentifikatorsiz view'da 403 ga tushiradi) — `WWW-Authenticate` sarlavhasi bilan.
- Logout boshqa foydalanuvchining refresh tokenini qabul qilmaydi (401).
- `pytest` dan `--no-migrations` olib tashlandi: 5-bosqichdagi `BtreeGistExtension` faqat migration orqali yaratiladi, testlar haqiqiy migration'larda ishlashi kerak.

**AI xatolari:**
- Bash heredoc ichida `'` va `ʻ` aralashgan matn bilan buyruq buzildi, hech bir fayl yozilmadi — fayllar Write vositasi bilan qayta yozildi.
- `UserAttributeSimilarityValidator` default holatda `username/first_name/last_name/email` ni tekshiradi, `full_name` ni emas. AI buni birinchi yozishda o'tkazib yubordi; "Yangi Mijoz" ismli foydalanuvchi `yangi.mijoz` parolini qo'ya olardi. Test (`test_register_rejects_weak_password[yangi.mijoz]`) ushladi, `user_attributes=("email", "full_name")` qo'shildi.
- ruff RUF001 o'zbekcha `ʻ`/`ʼ` harflarini "noaniq belgi" deb belgiladi. Bu TASK 10.1 talabi — qoida o'chirildi.

## 2-bosqich — Catalog + providers

**Prompt (qisqacha):** "davom et" — 2-bosqich (Service, Provider, ProviderService, CRUD + ruxsatlar, soft delete).

**Generatsiya qilindi:**
- `catalog.Service` — DB CHECK'lar: davomiylik 5–480 va 5 ga karrali (`Mod` ifodasi bilan), narx ≥ 0; unique slug. `services.py` (avtomatik unique slug, update, deactivate), `selectors.py`.
- `providers.Provider` + `ProviderService` — rang CHECK (`#RRGGBB`), unique(provider, service), `user` faqat `provider` rolidagi va boshqa xodimga bog'lanmagan foydalanuvchi. `set_provider_services` — ro'yxatni butunlay almashtiradi (tranzaksiyada).
- API: `/services`, `/providers` (ViewSet, PUT yo'q), `PUT /providers/{id}/services`, `?service=` filtr, `?include_inactive=1` (faqat admin). Ommaviy va admin serializer'lari alohida (ommaga `is_active`, `user_id` ko'rinmaydi).
- `apps/api/permissions.py` (`IsAdmin`, `IsAdminOrReadOnly`), `apps/api/utils.py` (noto'g'ri UUID → 404 / 422).
- Django admin: xizmat va xodimni o'chirish tugmasi o'chirilgan.
- Testlar: `test_services.py` (30), `test_providers.py` (26), `test_catalog_constraints.py` (9 — DB CHECK'lar ORM'siz ham ishlashi).

**Qanday tekshirildi:** `pytest` 112/112, qamrov 95%; `ruff`, `makemigrations --check` toza; dev bazaga migrate.

**Qarorlar:**
- DELETE = `is_active=False` (xizmat ham, xodim ham) — bronlar tarixi uchun. Qayta faollashtirish `PATCH {"is_active": true}`.
- Noto'g'ri UUID URL'da → 404 (500 emas), query parametrda → 422.
- Nofaol xizmat/xodim ommaga 404, admin'ga ko'rinadi (edge #10).
- Nom o'zgarganda slug o'zgarmaydi (UI havolalari buzilmasin); bo'sh slug yuborilsa nomdan qayta yasaladi.
- Provider.timezone `NULL` = biznes timezone'i (TASK 4.2); ruff DJ001 shu joyda `noqa` bilan izohlangan.
- TASK 5.5 dagi "N ta kelajak broni bor" ogohlantirishi bronlar paydo bo'lgach (5-bosqich) va UI'da (9-bosqich) qo'shiladi; hozir DELETE `204`.

**AI xatolari:**
- Ishlatilmagan `IsProvider` ruxsat klassi "keyinroq kerak bo'ladi" deb yozilgan edi — qamrov hisobotida ko'rinib qoldi, olib tashlandi (3-bosqichda haqiqiy ishlatilganda qo'shiladi).
- `update_service` dagi slug tarmoqlari testsiz qolgan edi (qamrov 83%) — 2 ta test qo'shildi.

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
