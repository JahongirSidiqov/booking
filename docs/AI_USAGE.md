# AI foydalanish jurnali

Loyiha Claude Code (Claude Opus) yordamida, TASK.md dagi 13 bosqich (0–12) bo'yicha qurildi. Har bosqich uchun: prompt qisqacha → nima generatsiya bo'ldi → qanday tekshirildi → nima o'zgartirildi → AI xatolari.

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

**Prompt (qisqacha):** "davom et" — 6-bosqich (state machine, transition service, status history, confirm/cancel/complete, bekor qilish siyosati, o'tishlar matritsasi).

**Generatsiya qilindi:**
- `apps/bookings/state_machine.py` — sof: `TRANSITIONS` jadvali, `Context`, guard'lar (`_not_started`, `_started`, `_cancel` — mijoz uchun deadline, xodim/admin uchun sabab majburiy), `check_transition`.
- `services.transition_booking` — `select_for_update(booking)`, ko'rinmasa 404, bekor qilish maydonlari (`cancelled_at/by/reason`), history. `auto_confirm` endi ham shu yo'ldan (`actor=None` → `system`).
- `Booking.save()` — service belgisisiz status o'zgarishini rad etadi (`StatusChangeError`).
- `selectors.visible_bookings / can_view / visible_booking` — mijoz o'ziniki, xodim faqat bog'langan provider'niki, admin hammasi.
- API: `GET /bookings`, `GET /bookings/{id}`, `POST /bookings/{id}/confirm|cancel|complete`. Javobga `customer`, `cancelled_at`, `cancel_reason` qo'shildi.
- `tests/test_architecture.py` (grep + model himoyasi), ADR-007.
- Testlar: `test_state_machine.py` (87 — 64 katakli matritsa + guard'lar), `test_booking_actions.py` (27), ikki admin parallel confirm (concurrency).

**Qanday tekshirildi:** `pytest` 396/396; `apps/bookings/*` va `views/bookings.py` qamrovi 100%, jami 98%. Matritsa testi kutilgan natijani TASK 5.3 jadvalidan mustaqil yozilgan `ALLOWED` lug'atidan hisoblaydi va `TRANSITIONS` ni unga solishtiradi.

**Qarorlar:**
- Xato tartibi: mavjud bo'lmagan o'tish 409 → noto'g'ri rol 403 → guard'lar. Sabab: yakuniy holatdagi bronni kim so'rasa ham bir xil javob.
- Xuddi shu holatga qayta o'tish — no-op emas, 409 (edge #23 da "409 yoki no-op" ruxsat berilgan; jadval bilan izchil bo'lishi uchun 409).
- Xodim/admin bekor qilganda sabab majburiy — `pending` dan ham (jadvalda faqat `confirmed` qatorida yozilgan; izchillik uchun ikkalasiga).
- `BookingStatusHistory` 5-bosqichda qo'shilgan edi; bu bosqichda barcha o'tishlar shunga yoziladi, alohida commit yo'q.
- Pagination va filtrlar — 7-bosqich (ro'yxat hozircha to'liq).

**AI xatolari:**
- Arxitektura grep testi birinchi ishga tushishda `apps/common/exceptions.py: self.status = status` ni ushladi — bu `DomainError` ning HTTP statusi, bron emas. Faylni istisno qilish o'rniga (tekshiruvni susaytiradi) atribut `http_status` ga qayta nomlandi.

## 7-bosqich — API polish

**Prompt (qisqacha):** "davom et" — 7-bosqich (problem-details handler, filtrlar/pagination/throttle, OpenAPI + Swagger, time off / ish vaqti o'zgarishida konflikt tekshiruvi).

**Generatsiya qilindi:**
- Konflikt tekshiruvi: `add_time_off` va `replace_availability` provider lock ostida faol bronlarni tekshiradi → `409 CONFLICTS_WITH_BOOKINGS` + `bookings` ro'yxati (edge #13, #14). Qamrov hisobi sof `slot_engine.uncovered`. ADR-005.
- Xato handler'i: exclusion `IntegrityError` har qanday yo'ldan → 409 (`CONSTRAINT_ERRORS` endi `common` da, `bookings.services` ham shundan foydalanadi); `OperationalError`/`InterfaceError` → `503 SERVICE_UNAVAILABLE` + `Retry-After` (edge #37); `/api/` ostidagi noma'lum URL va 500 → JSON (`apps/common/views.py`, `handler404/500`).
- `GET /bookings`: `PagePagination` (`page`, `page_size` 20/100, `count/page/page_size/total_pages/next/previous/results`), filtrlar `status` (vergul bilan), `provider`, `service`, `from`/`to` (ko'ruvchi zonasidagi kunlar), `upcoming=1` (eng yaqini birinchi), `tz`.
- OpenAPI: `drf-spectacular`, `/api/schema/`, `/api/docs/`. Barcha endpointlarga `@extend_schema` (summary, parametrlar, request/response, har xato kodi). Javob dict'lari haqiqiy serializer'larga o'tkazildi (`BookingSerializer`, `SlotsResponseSerializer`, `DaysResponseSerializer`, `AvailabilityResponseSerializer`, `DeactivationSerializer`) — sxema va javob bitta manbadan, bir-biridan uzoqlashmaydi. `ProblemSerializer` faqat hujjat uchun.
- Testlar: `test_schedule_conflicts.py` (8), `test_api_polish.py` (22), `test_exception_handler.py` (10), `uncovered` unit testlari, edge #12 alohida testi.

**Qanday tekshirildi:**
- `pytest` 438/438, qamrov 99% (`common/exceptions.py`, `slot_engine.py`, `bookings/*` 100%).
- `manage.py spectacular --validate --fail-on-warn` — 0 ogohlantirish; test ham shuni chaqiradi va har operatsiyada `summary` borligini tekshiradi.
- Javoblarni serializer'ga o'tkazishdan oldin va keyin eski testlar o'zgarishsiz o'tdi — shakl bayt-bayt bir xil qoldi (faqat ro'yxat pagination bilan o'raldi, 2 test yangilandi).
- 8-bo'limdagi har case uchun `test_edge_XX_` nomli test borligi skript bilan tekshirildi: faqat #29 (email, 10-bosqich) va #33 (UI, 8-bosqich) qoldi.

**Qarorlar:**
- Pagination faqat `GET /bookings` da. Xizmat va xodim ro'yxatlari kichik va chegaralangan, UI ularni to'liq ko'rsatadi.
- Noma'lum `IntegrityError` (biznes constraint emas) ataylab 500 bo'lib qoladi — bu bug, yashirilmasin.
- Xizmat/xodim ro'yxatida admin qo'shimcha maydonlarni ko'radi; OpenAPI'da ommaviy shakl + tavsifda izoh (polimorf sxema ortiqcha).

**AI xatolari / noaniqliklar:**
- Bir to'liq ishga tushishda **1 test yiqildi**, qaysi ekanini ko'rmay qoldim (natija faqat "1 failed"). Keyin 10 ta to'liq va 6 ta concurrency ishga tushishda qayta chiqmadi. Ehtimol test faylini tahrirlash bilan bir vaqtga to'g'ri kelgan, lekin isbotlanmagan — kuzatuvda.
- Ruff bitta chalkash assert'ni (`list(...)[0].hour`) belgiladi — `.get().start_time == time(9)` ga soddalashtirildi.

## 8-bosqich — UI (mijoz)

**Prompt (qisqacha):** "davom et" — 8-bosqich. Boshlashdan oldin TASK 10-bo'lim va `frontend-uiux-skill` o'qildi (mobile-first, bitta primary, holatlar, `ʻ`, Lucide, reduced-motion, placeholder yo'q).

**Generatsiya qilindi:**
- Asboblar (versiyalar qotirilgan): Tailwind CLI v4.3.3 (standalone, Node'siz), htmx 2.0.11, Alpine.js 3.17.4, Lucide 1.48.0 (faqat ishlatilgan 21 ta SVG), Inter 5.3.0 (latin + cyrillic woff2, loyiha ichida).
- `static/src/tokens.css` (TASK 10.2 tokenlari `@theme` da — CSS o'zgaruvchilari ham, utility'lar ham shu yerdan), `app.css` (btn/input/card/badge/chip/day/skeleton/toast/dialog komponentlari, `:focus-visible`, `prefers-reduced-motion`).
- `apps/web`: `text.py` (`ʻ` konstanta, `60 000 soʻm`, "Pa, 1-okt"), `templatetags/navbat.py` (`{% icon %}`, `status_badge`, filtrlar), `DisplayTimezoneMiddleware` (sahifalar foydalanuvchi zonasida, `/api/` dan tashqari), forms (`StyledFormMixin` — `aria-invalid`/`aria-describedby`), view'lar: `booking_flow.py`, `customer.py`, `account.py`.
- Shablonlar: `base.html` (skip-link, sticky navbar, timezone ogohlantirishi, `aria-live` toast — xato toasti o'zi yopilmaydi), `components/`, bron oqimi 4 qadam, `partials/time_picker.html` (HTMX), bronlarim (3 tab + empty state'lar), tafsilot (timeline + native `<dialog>` bilan bekor qilish), login/register/profile, 404/500.
- `scripts/build-css.ps1`, Dockerfile'da CSS build bosqichi, CI'da "commit qilingan CSS eskirmaganmi" tekshiruvi.
- Testlar: `tests/web/` (47), `tests/e2e/test_ui_browser.py` (4, Playwright + Chromium, o'rnatilmagan bo'lsa skip).

**Qanday tekshirildi:**
- `pytest` 489/489 (e2e bilan), qamrov 98%.
- **Haqiqiy brauzer (Playwright, headless Chromium):** 5 sahifa × 360px/1440px da gorizontal scroll yo'qligi; bron oqimi **faqat klaviatura** bilan (Tab/Space/Enter) boshidan oxirigacha; HTMX kun almashtirish sahifani qayta yuklamasligi va URL yangilanishi.
- Skrinshotlarni o'zim ko'rib chiqdim (360px va 1440px, har qadam) — quyidagi 3 ta muammo shu yo'l bilan topildi.

**Qarorlar:**
- Bron qadamlari query parametrlar bilan (`?provider=…&start=…`) — har qadamning URL'i bor, orqaga tugmasi ishlaydi, JS o'chiq bo'lsa ham forma ishlaydi (chiplar oddiy radio input).
- `409 SLOT_TAKEN` → 2-qadamga redirect, toast "Bu vaqt hozirgina band qilindi", slotlar yangidan, tanlov o'chgan. Tasdiq sahifasi ochilganda slot allaqachon band bo'lsa ham shu yo'l.
- Tasdiq formasida `idempotency_key` (uuid4) — ikki marta bosish bitta bron.
- Modal — native `<dialog>` (`showModal()`): focus trap, Esc, fon inert brauzerning o'zidan; body scroll `:has(dialog[open])` bilan.
- Skeleton faqat so'rov 300ms dan uzoq cho'zilsa ko'rinadi va layoutni surmaydi (absolute overlay).
- Tasdiq sahifasidagi ishonch mikromatnida "SMS/emailda eslatma" yo'q — eslatma funksiyasi yo'q, yolg'on va'da bo'lardi.
- Brauzer testlari CI'da ishlamaydi (Chromium yuklanmaydi) — lokal/qo'lda; hujjatlangan.

**AI xatolari:**
- Lucide SVG'lari litsenziya izohi (`<!-- ... -->`) bilan boshlanadi; ikonka tegi birinchi `>` ni `<svg>` tegi deb olardi. Fayllarni yuklab olgach ko'rib, ishlatishdan oldin tuzatildi.
- `@apply tabular` — o'zimning klassim, utility emas; Tailwind build yiqildi → `tabular-nums`.
- Tailwind CLI `-o` OneDrive papkasida `EEXIST mkdir` bilan yiqiladi (Bun runtime bug'i). CSS stdout orqali yoziladi; PowerShell 5.1 `>` UTF-16 ga o'girgani uchun `cmd /c` ishlatiladi.
- Bash heredoc'da `'` + `ʻ` aralash matn yana buzildi — shablonlar Write vositasi bilan qayta yozildi.
- **Testdagi xato:** kutilgan qiymat "Ch, 1-okt" TASK wireframe'dan ko'chirilgan edi. 2026-yil 1-oktabr — payshanba ("Pa"); wireframe 2025-yil kalendariga mos. Kod to'g'ri edi, test tuzatildi.
- **Brauzer testi topgan xato:** 360px da 1-qadam 82px keng. Sabab: `<fieldset>` brauzerda `min-width: min-content`, uzun xodim ismi `truncate` o'rniga sahifani kengaytirardi. Global `fieldset { min-width: 0 }`.
- **Skrinshotdan topilgan xatolar:** sana chizig'i 360px da `justify-between` + overflow tufayli chap tomoni kesilgan (tanlangan kun ko'rinmasdi), "51 boʻsh" ikki qatorga bo'linardi, ko'rinmas skeleton slotlar ustida ~150px bo'sh joy egallardi. Chiziq scroll + tanlangan kunni markazga olish, `whitespace-nowrap`, skeleton absolute overlay.
- Birinchi e2e ishga tushishda Google Fonts sabab `load` 30s timeout. Testni yumshatish o'rniga Inter loyiha ichiga olindi (tezroq birinchi ekran, tashqi bog'liqlik yo'q) — e2e 132s → 30s.
- Playwright `DJANGO_ALLOW_ASYNC_UNSAFE` ni funksiya darajasida qo'ygan edim — DB teardown modul darajasidagi brauzer ochiq paytda bo'ladi; modul darajasiga ko'chirildi.

## 9-bosqich — UI (dashboard)

**Prompt (qisqacha):** "davom et" — 9-bosqich (bugungi kun ko'rinishi, bronlar jadvali, xizmatlar/xodimlar/ish vaqti muharriri, sozlamalar).

**Generatsiya qilindi:**
- `state_machine`: "sabab majburiy" qoidasi guard'dan ma'lumotga ko'chirildi (`reason_required_for`), `available_targets(ctx)` — dashboard tugmalari server qabul qiladigan o'tishlardan hisoblanadi (tugma bor, server rad etadi — degan holat yo'q).
- `bookings/selectors`: qidiruv (`search`), `overlapping`, `day_kpis`, `upcoming_counts`.
- `apps/web/access.py` (`staff_required`, `admin_required`, `own_provider`), `forms_dashboard.py`, view'lar: `dashboard_bookings.py` (bugun, ro'yxat, tafsilot, amallar), `dashboard_catalog.py` (xizmatlar, xodimlar, deaktivatsiya), `dashboard_schedule.py` (ish vaqti, dam olish, sozlamalar).
- Shablonlar: sidebar layout (240px / mobil drawer, Esc bilan yopiladi), bugun (xodim ustunlari, ish vaqti oq / yopiq kulrang, bloklar xodim rangida, "hozir" chizig'i, 3 KPI), bronlar (filtrlar URL'da, desktop jadval / mobil card, sahifalash, tezkor tasdiqlash), tafsilot (mijoz kontakti `tel:`/`mailto:`, timeline, sababli bekor qilish dialogi), xizmat/xodim modal formalari (`?new=1`, `?edit=`), deaktivatsiya dialogi "N ta kelgusi bron" bilan, haftalik jadval muharriri (Alpine), dam olish ro'yxati, sozlamalar, 403.
- Staff login'dan keyin `/dashboard/` ga tushadi; navbar'da "Boshqaruv".
- Testlar: `tests/web/test_dashboard.py` (42), `available_targets` unit testlari (10), e2e: dashboard 8 sahifa × 360/1440 + mobil drawer va modal klaviatura bilan.

**Qanday tekshirildi:** `pytest` 544/544 (e2e bilan), qamrov 98% (`dashboard_bookings.py` 100%). Skrinshotlar 360px va 1440px da ko'rib chiqildi.

**Qarorlar:**
- Kun ko'rinishi o'qi kamida 09–19, ish vaqti yoki bron chetga chiqsa kengayadi; xodim qoidalari (o'z zonasida) ko'ruvchi zonasiga har sana uchun aylantiriladi.
- Bog'lanmagan xodim-foydalanuvchi bo'sh sahifa o'rniga tushuntirish ko'radi (edge #35).
- Dashboard ish vaqti muharriri Alpine'ga tayanadi (mijoz qismidan farqli, JS'siz ishlamaydi) — ichki xodimlar uchun qabul qilinadigan cheklov.
- Dam olish vaqti `datetime-local` bilan kiritiladi va xodimning zonasida talqin qilinadi; zona forma ustida yozilgan.
- Bekor qilishda UI ham sababni majburiy qiladi, server ham (state machine).

**AI xatolari (brauzer testlari va skrinshotlar topdi):**
- **Kun ko'rinishida bloklar tepaga yopishgan, ish vaqti ko'rinmagan.** Sabab: `LANGUAGE_CODE="uz"` da Django float'ni `69,231` deb chiqaradi — CSS'da noto'g'ri, brauzer deklaratsiyani tashlab yuboradi. Django testlari matnni tekshirgani uchun ushlamadi; skrinshotda ko'rindi. Foizlar view'da `f"{x:.3f}%"` qilib formatlanadi + regressiya testi.
- **Modal forma o'zi yopilib, sahifa qayta yuklanardi.** `dialog.close()` "close" hodisasini asinxron navbatga qo'yadi — u keyin qo'shilgan listener'ga tushib, sahifani tark etardi. `removeAttribute("open")` ga almashtirildi. Buni e2e test ("Execution context was destroyed") topdi.
- 360px da navbar 2px keng edi (staff uchun "Boshqaruv" + avatar, logo `min-w-0` siz qisqarmasdi).
- Konflikt ro'yxatida vaqt shablonda satr kesish bilan formatlangan edi ("2026-10-0104:00" chiqardi) — ko'rib chiqishda topildi, view'da mahalliy vaqtga formatlanadi.
- Tahrir paytida ikki marta skriptli almashtirish ko'p qatorli funksiya imzosiga mos kelmadi, ruff keyin "ishlatilmagan" importni o'chirdi — `F821` bilan ushlandi, qo'lda tuzatildi.
- `showModal()` fokusni yopish tugmasiga qo'yardi — formalarda birinchi maydonga `autofocus`.
- Test yozishda: `get_by_role("button", name="Menyu")` "Menyuni yopish" ga ham mos keldi → `exact=True`.

## 10-bosqich — Notifications

**Prompt (qisqacha):** "davom et" — 10-bosqich (create/confirm/cancel email'lari `on_commit` orqali, email xatosi bronni qaytarmasligi).

**Generatsiya qilindi:**
- `apps/notifications/senders.py`: `booking_created`, `booking_status_changed`; `_never_raise` (istisno → `logger.exception`), bron commit'dan keyin qayta o'qiladi, vaqt mijoz/xodim zonasida, havolalar `SITE_URL` bilan.
- `bookings/services.py`: `transaction.on_commit(partial(...))` — yaratishda va har o'tishda.
- Shablonlar `templates/emails/`: 5 ta xat × (txt + html). HTML — inline stil (email klientlari CSS o'zgaruvchilarini bilmaydi), txt — `autoescape off`.
- `SITE_URL` sozlamasi (`.env.example`), ADR-006.
- Testlar: `tests/notifications/test_emails.py` (15).

**Qanday tekshirildi:**
- `pytest` notifications 15/15.
- Mutatsion tekshiruv: (1) `_never_raise` ishlamasa → `test_edge_29` yiqildi; (2) xat `on_commit` siz, tranzaksiya ichida yuborilsa → `test_no_email_before_commit` yiqildi. Kuzatuv: `test_edge_37` bu mutatsiyada ham o'tdi — u yerda xato yuborish nuqtasidan oldin sodir bo'ladi; shuning uchun "commit'dan oldin yubormaslik" kafolatini `test_no_email_before_commit` tekshiradi.

**Qarorlar:**
- Kimga: mijozga — qabul qilindi / tasdiqlandi / bekor qilindi (xodim bekor qilsa sabab bilan, mijoz o'zi bekor qilsa tasdiq); xodimga (akkaunti bo'lsa) — yangi bron va mijoz bekor qilgani. "Bajarildi" — xat yo'q.
- `auto_confirm` → bitta "tasdiqlandi" xati; idempotent takrorlash → xat yo'q.
- Eslatma (uchrashuvdan oldin) xati yo'q — scheduler talab qiladi, v1 ko'lamida emas; UI'da ham va'da qilinmagan.

**AI xatolari:**
- Birinchi variantda mavzu (subject) satrlari juda uzun va takrorlanuvchi edi (ruff E501) — `when["label"]` bilan soddalashtirildi.
- Test fayli oxiriga mavzuga aloqasiz test (`…timestamps_are_utc_in_db`) qo'shib yuborilgan edi — olib tashlandi; `pytest.raises(Exception)` → `DomainError`.

## 11-bosqich — Ops

**Prompt (qisqacha):** "davom et" — 11-bosqich (prod Dockerfile/compose, healthz, seed_demo, expire_stale_bookings, CI, deploy qo'llanmasi).

**Generatsiya qilindi:**
- `/healthz` (DB ping → 200/503), `DisplayTimezoneMiddleware` uni chetlab o'tadi.
- `bookings.services.expire_stale_bookings` + `manage.py expire_stale_bookings`: har bron lock ostida qayta o'qiladi va faqat hali ham `pending` bo'lsa bekor qilinadi (sabab `expired`, `changed_by=None`, mijozga xat).
- `manage.py seed_demo`: 5 xizmat, 3 xodim (biri akkauntli), haftalik jadvallar, 1 dam olish, ~23 bron. Hamma bron service orqali; o'tganlari `unittest.mock.patch("django.utils.timezone.now")` bilan "o'sha paytda" yaratilgan — tarix vaqtlari ham ishonarli. Xatlar seed paytida o'chirilgan; bo'sh bo'lmagan bazada rad etadi.
- Tizim sabablari (`expired`, `auto_confirm`) UI va xatlarda odam tilida (`reason_text`).
- `docker/entrypoint.sh` rejimlari: `gunicorn` (migrate + collectstatic), `runserver`, `scheduler` (`while true; sleep & wait` + SIGTERM trap). `HEALTHCHECK`. `docker-compose.prod.yml` (db, web, scheduler, `--profile caddy`), `docker/Caddyfile`, `.env.prod.example`, `render.yaml`, `docs/DEPLOY.md`.
- Prod sozlamalari: `/healthz` SSL redirect'dan ozod, `localhost` + Render/Railway hostnomi avtomatik `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`SITE_URL` ga, `NUM_PROXIES=1`, HSTS preload ataylab o'chirilgan (sababi izohda).
- CI: `check --deploy --fail-level WARNING`, toza bazada `seed_demo`, yangi `compose-smoke` job (prod stekni ko'tarib `/healthz`, 301, hash'langan CSS, seed, scheduler logini tekshiradi).
- Testlar: `tests/test_ops.py` (10).

**Qanday tekshirildi:**
- `pytest` (to'liq ro'yxat quyida hisobotda); `manage.py check --deploy` prod sozlamalari bilan — 0 muammo (1 ta izohli silenced).
- `seed_demo` dev bazada ishga tushirildi: 23 bron (pending 6, confirmed 4, cancelled 3, completed 10); qayta ishga tushirish rad etildi.
- Prod `collectstatic` (`CompressedManifestStaticFilesStorage`) lokal ishga tushirildi va test sifatida qo'shildi.
- **Tekshirilmagan:** Docker image build va `docker compose` — mashinada Docker yo'q. CI `compose-smoke` job'i birinchi push'da tekshiradi.

**AI xatolari (hammasi deploydan oldin topildi):**
- **Prod konteyner ishga tushmas edi:** Tailwind manbasi (`static/src/app.css`, `@import "tailwindcss"`) `STATICFILES_DIRS` ichida edi — manifest `collectstatic` uni hal qila olmay yiqiladi, entrypoint `set -e` bilan to'xtaydi → crash loop. Prod `collectstatic` ni lokal ishga tushirish bilan topildi; manba `assets/css/` ga ko'chirildi + regressiya testi.
- **`/healthz` DB o'chganda 503 emas, 500 berardi:** middleware har sahifada `BusinessSettings` ni o'qirdi. Test topdi; middleware `/healthz` ni chetlab o'tadi.
- **CSS build skripti xatoni yashirardi:** manba yo'li o'zgargach Tailwind yiqildi, lekin skript "rebuilt" deb bo'sh `app.css` qoldirdi (`cmd >` faylni oldindan yaratadi). Endi vaqtinchalik faylga yoziladi va faqat muvaffaqiyatda almashtiriladi; ataylab buzib sinaldi.
- Python orqali PowerShell faylini tahrirlashda `css\app` dagi `\a` "bell" belgisiga aylandi (`csspp.css`) — yangi himoya build'ni to'xtatdi, fayl Write bilan qayta yozildi.
- `seed_demo` hisoboti Windows konsolida (cp1252) `ʼ` ni chiqara olmay yiqildi — buyruq chiqishi ASCII inglizchaga o'tkazildi (ma'lumotning o'zi o'zbekcha).
- `.gitignore` dagi `.env.*` `.env.prod.example` ni ham yashirardi — istisno qo'shildi.
- Birinchi yozilgan `HEALTHCHECK` ichma-ich qochirilgan qo'shtirnoqlar bilan mo'rt edi — exec shakliga soddalashtirildi.

## 12-bosqich — Hujjat va yakun

**Prompt (qisqacha):** "davom et" — 12-bosqich (ARCHITECTURE, EDGE_CASES, AI_USAGE, INTERVIEW_NOTES, README skrinshotlar va demo loginlar bilan, yakuniy tekshiruv).

**Generatsiya qilindi:**
- `docs/ARCHITECTURE.md` — qatlamlar, bron oqimi, DB sxemasi va constraint'lar, slot engine, state machine, vaqt zonalari, auth, xato formati, email, texnologiya tanlovi, trade-off'lar, o'sish rejasi.
- `docs/EDGE_CASES.md` — 38 ta holat: natija, yechim, test nomi (har bir nom grep bilan mavjudligi tekshirildi); curl namunalari; slot tekislash qoidasi.
- `docs/INTERVIEW_NOTES.md`, README (skrinshotlar, demo loginlar, ishga tushirish, sozlamalar, testlar, CI, hujjatlar), `LICENSE` (MIT).
- `docs/screenshots/` — `seed_demo` qilingan dev bazadan Playwright bilan 7 ta skrinshot (390px telefon, 1440px desktop).
- `tests/test_architecture.py::test_no_stray_control_characters_in_sources`.

**Qanday tekshirildi:** hujjatdagi har test nomi repoda borligi skript bilan; skrinshotlar ko'rib chiqildi (bo'sh kun ko'rinishi almashtirildi); yakuniy `ruff`, `pytest` (e2e bilan), `check --deploy`, 15-bo'lim checklist — natijalar hisobotda.

**AI xatolari:**
- **Hujjatdagi tekshiruv buyrug'i hech narsa tekshirmas edi:** EDGE_CASES'ga yozilgan PowerShell bir qatorligi `Select-String -Quiet` ga tayangan; Windows PowerShell 5.1 da u har fayl uchun alohida True/False massiv qaytaradi va `-not` hech qachon ishlamaydi. Birinchi natija ("38 ta hammasi bor") shuning uchun ma'nosiz edi — mavjud bo'lmagan `test_edge_99` bilan salbiy nazorat o'tkazilganda ko'rindi. Hisoblash `-List` + `.Count` ga o'zgartirildi, ijobiy va salbiy nazorat bilan qayta tekshirildi.
- **8-bosqichdan qolgan buzuq qator:** README va CLAUDE.md da `.\scripts\build-css.ps1` o'rnida `.\scripts<backspace>uild-css.ps1` turgan edi — Python qatoridagi `\b` backspace belgisiga aylangan. README'ni o'qishda topildi; bunday belgilarni butun repoda qidiradigan test qo'shildi (u darhol ikkala qatorni ushladi).
- Skrinshot skriptida yashirin (`sr-only`) radio'ni to'g'ridan-to'g'ri bosishga urinish — foydalanuvchi kabi card (label) bosiladigan qilindi.

## Bonus 1 — timezone tanlash (UI) va iCal eksport

**Prompt (qisqacha):** 12-bosqichdan keyin "davom et" — TASK 1-bo'limidagi bonuslar tartibda.

**Avval tekshirildi (qaysi bonuslar asosiy bosqichlarda bajarilgan):** sozlanadigan bekor qilish siyosati (sozlamalar + state machine), email (10), dashboard KPI (9), Swagger (7), prod compose profili (11). Yangi qilinishi kerak: timezone UI (qisman), iCal, buffer time, "istalgan xodim".

**Generatsiya qilindi:**
- Timezone: anonim foydalanuvchi zonasi sessiyada (`DisplayTimezoneMiddleware`: profil → sessiya → biznes, sessiyadagi qiymat IANA bo'yicha qayta tekshiriladi), `POST /timezone/`, ogohlantirish chizig'ida "Qurilma zonasiga oʻtish" tugmasi.
- iCal: `apps/bookings/ical.py` — sof RFC 5545 generatori (escape, oktet bo'yicha 75 belgili qator bo'lish, CRLF, UID, `SEQUENCE`, `STATUS`), `GET /api/v1/bookings/{id}/ical` va `/bookings/<id>/ical/` (faqat egasi), natija va tafsilot sahifalarida havola.
- Testlar: `tests/unit/test_ical.py` (9), `tests/web/test_bonus_ical_timezone.py` (13), e2e: Dubay zonasidagi qurilma → chiziq → bir bosish.

**Qanday tekshirildi:** `pytest` 593/593 (e2e bilan), OpenAPI `--fail-on-warn` toza; Dubay zonasini emulyatsiya qilib skrinshot ko'rib chiqildi.

**Qarorlar:** kutubxonasiz iCal (bitta VEVENT uchun ortiqcha bog'liqlik); `.ics` faqat bron egasiga (TASK 6.1: "egasi"), provider/admin'ga 404; bekor qilingan bron uchun havola ko'rsatilmaydi, lekin fayl `STATUS:CANCELLED` bilan olinadi.

**AI xatolari:**
- Qator bo'lishni belgilar bo'yicha emas, **oktet** bo'yicha qilish kerakligi oldindan hisobga olindi (`ʻ` UTF-8 da 2 bayt); test ko'p baytli belgi bo'linmasligini tekshiradi.
- `<p>` ichiga `<form>` qo'yilgan edi (noto'g'ri HTML — brauzer paragrafni erta yopadi) — `<div>` ga almashtirildi.
- Yangi chiziq tugmasi e2e login yordamchisini buzdi: `page.click("button[type=submit]")` endi yashirin chiziq tugmasini birinchi topib, 30 soniya kutardi (7 test yiqildi, suite 4 barobar sekinlashdi). Selektor `main` bilan cheklandi.
- 360px skrinshotda tugma matnni tor ustunga siqib qo'ygan, bosish maydoni ~20px edi — mobilda alohida qatorga va 44px maydonga o'tkazildi.
- OpenAPI tavsifida ASCII apostrof (`o'chiradi`) — apostrof testi ushladi.

## Nimani o'zim yozdim / o'zgartirdim

Rostini aytganda: **ilova kodining deyarli hammasini AI yozdi.** Bu sessiyada kuzatilgan inson hissasi:

- **Texnik topshiriq** — `TASK.md` (bosqichlar, talablar, edge case'lar, dizayn tokenlari, qabul mezonlari) va ish qoidalari (bosqichma-bosqich, test o'tmasa to'xtash, placeholder yo'q).
- **Har bosqich natijasini ko'rib, keyingisiga ruxsat berish** ("davom et") — 0–12 bosqichlar.
- **Muhit qarorlari:** Docker Desktop o'rniga lokal PostgreSQL 18 ishlatish; `postgres` parolini tiklash va `navbat` rolini yaratish (AI bergan skriptni administrator PowerShell'da o'zi ishga tushirdi).
- Loyiha nomi, demo biznes, rollar, stack va ko'lam (multi-tenant, to'lov, SMS yo'q) — TASK.md dan.

AI ning o'zi qabul qilgan va ADR/jurnalda yozilgan qarorlar (tasdiqlash uchun ko'rib chiqish kerak): refresh token oilasi, xato handler'ini 7-bosqichdan oldinga surish, `BookingStatusHistory` ni 5-bosqichda qo'shish, xodim `pending` bronni bekor qilganda ham sabab majburiyligi, qayta tasdiqlashda no-op emas 409, seed uchun soatni `mock` bilan orqaga surish, MIT litsenziya.

Keyin kodni qo'lda o'zgartirsangiz, shu bo'limga nimani va nega o'zgartirganingizni qo'shing — baholashda aynan shu farq ko'rinishi kerak.

## Umumiy natija

| Ko'rsatkich | Qiymat |
|---|---|
| Bosqichlar | 13 (0–12), har biri alohida tasdiqlangan |
| Testlar | 593 (unit, API, web, concurrency, email, e2e) — hammasi yashil |
| Qamrov | ~98% |
| TASK 8-bo'limdagi holatlar | 38/38, har biri nomli test bilan |
| ADR | 9 (001–009) |
| Faqat brauzer/skrinshot topgan xatolar | 8 ta (fieldset kengligi, sana chizig'i, skeleton bo'shlig'i, CSS'dagi vergulli foizlar, dialog o'zi yopilishi, navbar 2px, tashqi shrift timeout'i, tahrirlashdagi ASCII belgilari) |
| Tekshirilmagan | Docker image build va `docker compose` (mashinada Docker yo'q) — CI'dagi `compose-smoke` job'i birinchi push'da tekshiradi; haqiqiy SMTP va deploy |
