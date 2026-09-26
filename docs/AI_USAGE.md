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

**Prompt (qisqacha):** "davom et" — 3-bosqich (availability rules, time off, business settings).

**Generatsiya qilindi:**
- `scheduling` modellari: `AvailabilityRule` (mahalliy `time`, CHECK start < end va weekday 0–6), `TimeOff` (CHECK, index `(provider, start_at)`), `BusinessSettings` (singleton `pk=1`, CHECK: step ∈ {5,10,15,20,30,60}, max advance 1–365, lead time ≤ 7 kun, deadline ≤ 14 kun).
- `services.py`: `replace_availability` (butun hafta bitta PUT, bir kunda kesishish → 422, provider qatoriga `select_for_update`), `add_time_off`, `delete_time_off`, `update_settings`. `selectors.py`: effektiv timezone, qoidalar, time off ro'yxati.
- API: `GET/PUT /providers/{id}/availability`, `GET/POST /providers/{id}/time-off`, `DELETE /providers/{id}/time-off/{id}`, `GET/PATCH /settings` (ommaga qisqa, admin'ga to'liq).
- `IsProviderOwnerOrAdmin` + `can_manage_provider` (edge #35), `AwareDateTimeField` (offset'siz datetime → 422).
- ADR-004 (yarim tundan o'tmaslik), ADR-009 (UTC saqlash, offset majburiy).
- Testlar: `test_availability.py` (24), `test_time_off.py` (13), `test_settings.py` (13), `test_scheduling_constraints.py` (7).

**Qanday tekshirildi:** `pytest` 164/164, qamrov 97%; `ruff`, `makemigrations --check` toza; dev bazaga migrate.

**Qarorlar:**
- `BusinessSettings` ma'lumot migratsiyasi bilan emas, `load()` (`get_or_create(pk=1)`) bilan yaratiladi: 5-bosqichdagi `TransactionTestCase` jadvallarni tozalaydi, migratsiyadagi qator yo'qolib qolardi.
- Jadval o'zgarishi ham provider qatorini lock qiladi — keyin bron yaratish ham shu qatorni lock qiladi, shuning uchun qoida o'zgarishi va bron tekshiruvi aralashib ketmaydi.
- Yonma-yon oraliqlar (09–13, 13–18) ruxsat etiladi — `[)` semantikasi.
- Boshqa xodimning jadvaliga kirish — 403 (xodim ommaviy obyekt, mavjudligini yashirish shart emas); boshqa xodimning time off id'si — 404.
- Time off ro'yxati default holatda faqat tugamaganlarini ko'rsatadi, `?include_past=1` — hammasini.
- Bron bilan konflikt tekshiruvi (`409 CONFLICTS_WITH_BOOKINGS`, edge #13/#14) TASK 14-bo'limiga ko'ra 7-bosqichda.

**AI xatolari:**
- Hech biri testda chiqmadi. ruff `zip(windows, windows[1:])` o'rniga `itertools.pairwise` ni taklif qildi — qabul qilindi.
- `AwareDateTimeField` dagi noto'g'ri sana (`2026-02-30`) tarmog'i testsiz edi — test qo'shildi.

## 4-bosqich — Slot engine

**Prompt (qisqacha):** "davom et" — 4-bosqich (sof slot engine, unit testlar, slots/days endpointlari).

**Generatsiya qilindi:**
- `apps/scheduling/slot_engine.py` — DB'siz, soatsiz funksiyalar: `get_available_slots`, `get_day_summary`, `subtract`, `merge`, `align_to_step`, `rule_windows`, `local_day_bounds`, `validate_range`. Kirish/chiqish faqat aware UTC; qoidalar har sana uchun alohida UTC'ga aylantiriladi.
- `scheduling/selectors.py`: `bookable_pair` (404 / `INACTIVE_RESOURCE` / `PROVIDER_NOT_OFFERING_SERVICE` — 5-bosqichda bron yaratish ham shuni ishlatadi), `day_slots`, `days_summary`.
- API: `GET /availability/slots`, `GET /availability/days`; `tz` tartibi: `?tz=` → foydalanuvchi profili → biznes.
- `docs/EDGE_CASES.md` — slot tekislash qoidasi (TASK 5.1 talabi); to'liq jadval 12-bosqichda.
- Testlar: `tests/unit/test_slot_engine.py` (35), `tests/api/test_slots.py` (20).

**Qanday tekshirildi:**
- `pytest` 219/219; `slot_engine.py` qamrovi 100%, jami 97%.
- **Mutatsion tekshiruv (qo'lda):** engine'ga ataylab ikki xato kiritildi — (1) davomiylik sig'ishini tekshirmaslik → 9 test yiqildi; (2) "hozir" boshlanadigan slotga ruxsat → 1 test yiqildi (`test_edge_04`). Kod qaytarildi, testlar yashil. Maqsad — qo'lda hisoblangan kutilgan qiymatlar haqiqatan xatoni ushlashini ko'rish.
- Kutilgan qiymatlar qo'lda hisoblandi: 09:00–18:00, 30 daq, step 15 → 35 slot; Tokyo/Tashkent kesimida 11 slot; Berlin DST'da 09:00 CEST = 07:00Z, 09:00 CET = 08:00Z.

**Qarorlar:**
- Step setkasi mahalliy yarim tunga bog'langan (UTC'ga emas) — +5:45 zonalarda ham 09:00/09:30.
- Mijozning bir kuni xodimning ikki sanasiga tushishi mumkin (edge #38) — engine ikkala sananing qoidalarini oladi va natijani mijoz kuniga qirqadi.
- "Hozir" boshlanadigan slot — o'tmish (`start > now`, edge #4).
- `max_advance_days` chegarasi inklyuziv (`start ≤ now + N kun`).
- 31 kunlik chegara inklyuziv (1–31 oktyabr ruxsat, 32 kun → `400 RANGE_TOO_LARGE`).
- Bronlar hali yo'q: engine `busy_ranges` ni parametr sifatida qabul qiladi va testlarda ishlatiladi; API 5-bosqichda bronlarni uzata boshlaydi.

**AI xatolari:**
- `_query_window` birinchi yozilishida naive `datetime.astimezone()` ishlatilgan — bu server mashinasining lokal zonasini oladi. ±1 kun zaxira tufayli testda ko'rinmas edi; kodni o'qish paytida AI o'zi topdi va aniq `tzinfo=UTC` ga o'zgartirdi.
- Birinchi yozilgan `test_bad_query_is_422` chalkash (ichida if-lar) edi — oddiy parametrlangan testga qayta yozildi.
- `align_to_step` dagi DST "takrorlanuvchi soat" tarmog'i testsiz edi — New York 2026-11-01 01:30 (ikkinchi marta) testi qo'shildi.

## 5-bosqich — Booking create + concurrency

**Prompt (qisqacha):** "davom et" — 5-bosqich (booking modeli, exclusion constraint'lar, `create_booking` provider lock bilan, idempotency, concurrency testi, ADR-003).

**Generatsiya qilindi:**
- `bookings.Booking` — snapshot maydonlar, `PROTECT`, 2 ta `ExclusionConstraint` (`[)`, faqat `pending|confirmed`), idempotency unique, CHECK'lar, 3 ta index. `BookingStatusHistory` — append-only (model va queryset darajasida update/delete taqiqlangan). Migratsiyaga `BtreeGistExtension()` qo'lda birinchi qo'shildi.
- `slot_engine.slot_rejection` — aniq vaqt uchun rad sababi; hukm `get_available_slots` ning o'zidan (bitta haqiqat manbai).
- `bookings/services.create_booking` — provider lock → idempotency (lock ichida) → `bookable_pair` → engine → mijoz kesishuvi → insert → history; `IntegrityError` constraint nomi bo'yicha 409; `auto_confirm` (edge #36).
- `POST /api/v1/bookings` (faqat `customer`, `Idempotency-Key`, 10/min throttle), javob TASK 6.4 shaklida. Slots API endi band vaqtlarni ayiradi. `DELETE /services|providers/{id}` endi 200 + kelgusi bronlar ro'yxati (edge #25).
- Django admin'da bron faqat o'qish uchun (status service'dan tashqarida o'zgarmasin).
- ADR-003, ADR-008.
- Testlar: `test_bookings.py` (35 — edge #2–#12, #17, #24, #25, #31, #32, #36), `test_booking_constraints.py` (10), `test_booking_service.py` (3), `tests/concurrency/test_double_booking.py` (5), `slot_rejection` unit testlari (11), admin testi.

**Qanday tekshirildi:**
- `pytest` 281/281; qamrov jami 98%, `bookings/services.py` va `slot_engine.py` 100%.
- Concurrency: 10 thread `threading.Barrier` bilan haqiqiy PostgreSQL'da → 1×201, 9×409.
- **Ikki qatlam haqiqatan ishlashini o'lchash:** vaqtincha probe test (keyin o'chirildi) constraint'ga yetgan yutqazuvchilarni sanadi, 3 marta: lock bilan 0/9, lock'siz 1–2/9. Ya'ni lock poygani tartibga soladi, lock'siz esa constraint haqiqatan oxirgi qalqon. Bu sonni assert qilmadim — thread vaqtiga bog'liq, test beqaror bo'lardi.
- Bir xil kalit bilan 5 parallel retry → 1×201 + 4×200 replay.

**Qarorlar:**
- Idempotency tekshiruvi lock ichida (aks holda parallel double-click ikkinchi so'rovga `SLOT_TAKEN` berardi).
- Bir xil kalit + boshqa payload → sha256 fingerprint orqali `409 IDEMPOTENCY_MISMATCH`; kalit mijoz bo'yicha.
- `BookingStatusHistory` hozir qo'shildi (14-bo'limda 6-bosqichda) — bron yaratish oqimi (3.3, 10-qadam) va javob shakli (6.4) history'ni talab qiladi. 6-bosqichda holat o'tishlari shu jadvalga yoziladi.
- `auto_confirm` hozircha `create_booking` ichida to'g'ridan-to'g'ri; 6-bosqichda umumiy `transition_booking` ga o'tkaziladi.
- Bron ro'yxati/tafsiloti (`GET /bookings`) 6–7-bosqichlarda.

**AI xatolari:**
- `django.utils.timezone.UTC` ishlatilgan — bunday atribut yo'q (Django 5 da `timezone.utc` ham olib tashlangan). Birinchi ishga tushirishdan oldin kodni o'qib topildi, `datetime.UTC` ga o'zgartirildi.
- `_replay` `None` qaytarishi mumkin bo'lgan yo'lda natija tekshirilmagan edi — tuzatildi.
- Skriptli qidir-almashtir o'z oldingi almashtirishiga qoqilib, fayl yozilmadi — fayl butunlay qayta yozildi.
- **freezegun + DRF throttle:** 31 test `TypeError: fake_time() takes 0 positional arguments` bilan yiqildi. Sabab: `SimpleRateThrottle.timer = time.time` klass yaratilganda saqlanadi; modul birinchi marta freezegun bloki ichida import qilinsa, soxta funksiya klass atributiga tushib, metod sifatida bog'lanadi. `tests/conftest.py` da modul oldindan import qilinadi (izoh bilan).
- Test yordamchi funksiyasi `customer_client()` pytest fixture nomini soya qilib qo'ygan — `new_customer()` ga o'zgartirildi.
- `Booking.is_active` property ishlatilmagan — qamrov hisobotida ko'rinib, olib tashlandi.
- Soxta `IntegrityError.__cause__` uchun `SimpleNamespace` ishlatilgan — Python faqat exception qabul qiladi; kichik exception klassi bilan almashtirildi.

## 6-bosqich — State machine

## 7-bosqich — API polish

## 8-bosqich — UI (mijoz)

## 9-bosqich — UI (dashboard)

## 10-bosqich — Notifications

## 11-bosqich — Ops

## 12-bosqich — Hujjat va yakun

## Nimani o'zim yozdim / o'zgartirdim
