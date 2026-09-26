# NAVBAT — Appointment Booking System
## Claude Code uchun to'liq texnik topshiriq (Django)

> **Qanday ishlatiladi:** bu faylni yangi papkaga `TASK.md` nomi bilan saqlang, papkada Claude Code'ni oching va 16-bo'limdagi birinchi xabarni yuboring. Claude Code 14-bo'limdagi bosqichlar tartibida ishlaydi, har bosqichdan keyin commit qiladi va hisobot beradi.

---

## 0. Claude Code uchun ish qoidalari (majburiy)

1. **Bosqichma-bosqich ishla** — 14-bo'limdagi tartibda. Bir bosqich tugamaguncha keyingisiga o'tma. Bosqich = kod → test → hujjat → commit.
2. **Har bosqich boshida** 3–6 qatorli reja ko'rsat (nima qurasan, qaysi fayllar). **Har bosqich oxirida** hisobot: nima qilindi, qanday qaror qabul qilindi, foydalanuvchi qo'lda nimani tekshirishi kerak.
3. **Git:** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). Bitta commit = bitta mantiqiy o'zgarish. Bosqich ichida 2–5 commit bo'lishi normal. Tarix bosqichma-bosqich ishlanganini ko'rsatishi shart — bu baholash mezoni.
4. **Qarorlar:** har muhim texnik qaror uchun `docs/decisions/ADR-0NN-nomi.md` (Kontekst → Variantlar → Tanlov → Sabab → Oqibatlar). Minimal ADR ro'yxati 13.4-bo'limda.
5. **AI foydalanish jurnali:** `docs/AI_USAGE.md` — har bosqichda: qaysi qism generatsiya qilindi, qanday tekshirildi (test / qo'lda / o'qib), nima o'zgartirildi, qaysi joyda AI xato qildi. Bu fayl baholanadi — rostini yoz.
6. **Kod izohi:** murakkab joylarga (slot generatsiya, lock, state machine, timezone) "nima uchun shunday" izohi. "Nima qilyapti" izohi yozma — kod o'zi aytadi.
7. **Placeholder, TODO, mock data relizga kirmaydi.** Test o'tmasa — keyingi bosqich yo'q.
8. **Muhit:** Windows + PowerShell + Docker Desktop. Buyruqlarni PowerShell uchun yoz. PostgreSQL faqat Docker'da (lokal o'rnatish shart emas).
9. **UI bosqichidan oldin** `frontend-uiux-skill` o'rnatilgan bo'lsa uni o'qi; bo'lmasa 10-bo'limdagi tokenlar va qoidalar yetarli.
10. **Sen bilmagan narsani o'ylab topma.** Kutubxona API'sida ishonchsiz bo'lsang — `pip show` / docs tekshir yoki foydalanuvchidan so'ra.

---

## 1. Mahsulot

**Nima:** xizmat ko'rsatuvchi kichik biznes (sartaroshxona, go'zallik saloni, stomatologiya, repetitor, massaj) uchun onlayn navbat/bron tizimi. Demo brend: **Navbat**. Demo biznes: "Navbat Barbershop" (3 xodim, 5 xizmat).

**Rollar:**

| Rol | Nima qiladi |
|---|---|
| **Customer (mijoz)** | Ro'yxatdan o'tadi, xizmat va xodimni tanlaydi, bo'sh vaqtlarni ko'radi, bron qiladi, o'z bronlarini ko'radi va bekor qiladi |
| **Provider (xodim)** | O'z kunlik jadvalini ko'radi, o'z bronlarini Confirm / Complete qiladi, o'z ish vaqtini (availability) belgilaydi |
| **Admin (biznes egasi)** | Xizmatlar, xodimlar, availability, barcha bronlar, statuslar, sozlamalar (timezone, bekor qilish siyosati) |

**Ko'lam (v1 — majburiy):**
- Service CRUD (name, description, duration, price, is_active)
- Provider CRUD + provider qaysi xizmatlarni ko'rsatadi
- Availability: haftalik takrorlanuvchi ish vaqti + ta'til/dam olish (time off)
- Bo'sh slotlarni ko'rish (kun va sana oralig'i bo'yicha)
- Bron yaratish (double booking mumkin emas — DB darajasida kafolat)
- Status: `pending` → `confirmed` → `completed`, istalgan faol holatdan `cancelled`
- Booking history (mijoz uchun ro'yxat + har bron uchun status timeline)
- REST API (JWT) + HTML UI (session)
- Validation, xato formati, throttling
- Testlar (shu jumladan concurrency testi), Docker, README, ARCHITECTURE, EDGE_CASES

**Bonus (v1 tugagach, shu tartibda):** timezone tanlash (UI) → cancellation policy (sozlanadigan) → email notification → admin dashboard KPI → API docs (Swagger) → Docker Compose prod profili → iCal (.ics) eksport → buffer time → "istalgan xodim" (any provider).

**Ataylab qilinmaydi (ADR-001):** multi-tenant (bir nechta biznes), onlayn to'lov, SMS, mobil ilova, recurring bookings.

---

## 2. Texnologik stack va sabablar

| Qatlam | Tanlov | Sabab |
|---|---|---|
| Til / framework | Python 3.12, **Django 5.x** | ORM + migrations + admin + auth tayyor; bir kishilik loyihada tezlik |
| API | **Django REST Framework** | Serializer/permission/throttle/pagination standart; OpenAPI uchun `drf-spectacular` |
| DB | **PostgreSQL 16** (majburiy) | `EXCLUDE ... USING gist` — double booking'ni DB darajasida taqiqlash. SQLite buni qila olmaydi, shuning uchun testlar ham Postgres'da |
| Auth | `djangorestframework-simplejwt` (API) + Django session (HTML UI) | API uchun stateless JWT (access 15 daq, refresh 7 kun, rotation + blacklist); UI uchun oddiy session |
| UI | **Django templates + HTMX + Alpine.js + Tailwind CSS** | Bitta deploy, bitta stack; slot picker HTMX partial bilan yangilanadi; SPA murakkabligi kerak emas |
| Email | Django `EmailBackend` (dev: console, prod: SMTP), `transaction.on_commit` | Celery/Redis'siz — bir jarayon, kam qism. Kechikish muammo bo'lsa keyin queue qo'shiladi (ADR-006) |
| Test | `pytest`, `pytest-django`, `factory_boy`, `freezegun` | |
| Sifat | `ruff` (lint + format), `pre-commit` | |
| Deploy | Docker (multi-stage), `docker compose`, Gunicorn + WhiteNoise, GitHub Actions CI | |
| Config | `django-environ`, `.env.example` | 12-factor |

**Frontend qarorining izohi (ADR-002):** talab "Backend API" — API to'liq DRF'da, hujjatlangan, testlangan. HTML UI esa shu API bilan **bir xil service qatlamini** chaqiradi (API ham, UI ham `services/` ustida yupqa qatlam). Shunday qilib biznes mantiq bir joyda, ikki interfeys. React SPA muqobili ADR'da yozilsin, lekin qurilmasin.

---

## 3. Arxitektura

### 3.1 Qatlamlar

```
HTTP
 ├─ api/        DRF ViewSets / APIViews  → serializer (shape + oddiy validatsiya)
 └─ web/        Django views + templates → forms (shape + oddiy validatsiya)
        │
        ▼
 services/      biznes qoidalari, transaction, lock, state machine   ← YAGONA yozish nuqtasi
 selectors/     o'qish so'rovlari (queryset'lar), slot engine (pure funksiyalar)
        │
        ▼
 models/        maydonlar, DB constraint'lar, index'lar (mantiqsiz)
```

**Qoidalar:**
- View'da biznes mantiq yo'q. View: input → service → output.
- `Booking.status` ni faqat `bookings/services.py` o'zgartiradi. `booking.status = ...; booking.save()` boshqa joyda taqiqlangan (test bilan tekshiriladi: grep + `save()` override).
- Model `save()` ichida cross-model logika yo'q.
- Slot engine — pure funksiyalar (DB'siz, vaqtni parametr sifatida oladi) → unit testga oson.
- Service funksiyalari domen xatolarini `common.exceptions.DomainError(code, message, status)` bilan ko'taradi; API va UI uni bir xil formatga aylantiradi.

### 3.2 Papka tuzilishi

```
navbat/
├── config/                 settings/{base,dev,test,prod}.py, urls.py, asgi/wsgi
├── apps/
│   ├── common/             DomainError, exception handler, BaseModel(uuid, created, updated), utils/time.py
│   ├── accounts/           User (email login, role), JWT views, register
│   ├── catalog/            Service
│   ├── providers/          Provider, ProviderService
│   ├── scheduling/         AvailabilityRule, TimeOff, BusinessSettings, slot_engine.py
│   ├── bookings/           Booking, BookingStatusHistory, services.py, selectors.py, state_machine.py
│   ├── notifications/      email templates, senders (on_commit)
│   ├── api/                v1/ routers, serializers, permissions, throttles, openapi
│   └── web/                HTML views, forms, templates/, static/
├── templates/              base.html, partials/
├── static/                 css (tailwind build), js (htmx, alpine)
├── tests/                  unit/, api/, web/, concurrency/, factories.py, conftest.py
├── docs/                   ARCHITECTURE.md, EDGE_CASES.md, AI_USAGE.md, decisions/ADR-*.md
├── docker/                 Dockerfile, entrypoint.sh
├── docker-compose.yml      db + web (dev)
├── docker-compose.prod.yml
├── .github/workflows/ci.yml
├── .env.example
├── pyproject.toml          ruff, pytest config
├── manage.py
├── README.md
└── TASK.md                 (shu fayl)
```

### 3.3 Bron yaratish oqimi (asosiy use case)

```
POST /api/v1/bookings  {service_id, provider_id, start_at, note, [Idempotency-Key header]}
   │
   ▼ serializer: format, majburiy maydonlar
   ▼ services.create_booking(customer, service_id, provider_id, start_at, note, idempotency_key)
        1. idempotency_key bor va shu mijozda ishlatilgan → mavjud bronni qaytar (200)
        2. transaction.atomic()
        3. Provider.objects.select_for_update().get(id)      ← shu xodim uchun so'rovlar navbatga tiziladi
        4. tekshir: service.is_active, provider.is_active, provider xizmatni ko'rsatadi
        5. end_at = start_at + service.duration
        6. tekshir: start_at step'ga mos, o'tmishda emas, lead time, max advance
        7. tekshir: slot availability rule ichida, time off bilan kesishmaydi
        8. tekshir: faol bron bilan kesishmaydi (mijoz uchun ham, xodim uchun ham) → do'stona 409
        9. Booking.objects.create(...)                        ← DB EXCLUDE constraint = oxirgi qalqon
       10. BookingStatusHistory(None → pending)
       11. transaction.on_commit(lambda: send_booking_created(booking))
   ▼ IntegrityError (exclusion) → DomainError("SLOT_TAKEN", 409)
   ▼ 201 + booking JSON
```

Nega ikkalasi ham (lock + constraint)? Lock — poyga holatida ikkinchi so'rov **kutib**, keyin do'stona xato oladi (500 emas). Constraint — lock aylanib o'tilgan har qanday yo'l (admin panel, shell, kelajakdagi bug) uchun kafolat. Ikkalasisiz ham tizim buziladi: faqat lock — mantiq xatosidan himoya yo'q; faqat constraint — foydalanuvchi IntegrityError'ni ko'radi va har bir poyga 500 beradi.

---

## 4. Database design

### 4.1 ER

```
User 1───0..1 Provider ──< ProviderService >── Service
 │              │                                │
 │              ├──< AvailabilityRule            │
 │              ├──< TimeOff                     │
 │              │                                │
 └──< Booking >─┘────────────────────────────────┘
        │
        └──< BookingStatusHistory
BusinessSettings (singleton)
```

### 4.2 Jadvallar

Barcha modellar `BaseModel`dan: `id UUID pk`, `created_at`, `updated_at`. Barcha vaqt ustunlari `timestamptz` (UTC), `USE_TZ=True`.

**accounts.User** (`AbstractBaseUser` + `PermissionsMixin`, `USERNAME_FIELD = email`)
- `email` unique, lowercase saqlanadi
- `full_name` (max 120)
- `phone` (E.164 yoki `+998XXXXXXXXX`, ixtiyoriy)
- `role`: `customer | provider | admin`
- `timezone` (IANA, default `Asia/Tashkent`)
- `is_active`, `is_staff`

**catalog.Service**
- `name` (max 100), `slug` unique, `description` (text)
- `duration_minutes` — CHECK `5 ≤ x ≤ 480` va `x % 5 = 0`
- `price` Decimal(12,2), CHECK `≥ 0`, valyuta UZS (sozlamada)
- `is_active`, `sort_order`
- **Hech qachon hard delete emas** — `is_active=False`. Sabab: bronlar tarixi.

**providers.Provider**
- `user` OneToOne(User, null=True) — xodim tizimga kirmasligi ham mumkin
- `name`, `bio`, `color` (hex, kalendar uchun), `is_active`
- `timezone` (null → biznes timezone'i)

**providers.ProviderService** — `provider`, `service`, unique(provider, service)

**scheduling.AvailabilityRule** (haftalik takror)
- `provider`, `weekday` (0=Dush … 6=Yak), `start_time`, `end_time` (mahalliy vaqt, xodim tz)
- CHECK `start_time < end_time` (yarim tundan o'tuvchi smena v1'da yo'q — ADR-004)
- Bir kunda bir nechta oraliq mumkin (09:00–13:00, 14:00–18:00); kesishish service qatlamida taqiqlanadi

**scheduling.TimeOff**
- `provider`, `start_at`, `end_at`, `reason`; CHECK `start_at < end_at`
- Index (provider, start_at)

**scheduling.BusinessSettings** (singleton, `pk=1`)
- `name`, `timezone` (default `Asia/Tashkent`), `currency` (`UZS`)
- `slot_step_minutes` (default 15; 5/10/15/20/30/60)
- `min_lead_time_minutes` (default 60) — hozirdan kamida shuncha keyin
- `max_advance_days` (default 30)
- `cancellation_deadline_hours` (default 24) — mijoz shundan kech bekor qila olmaydi
- `auto_confirm` (default False → yangi bron `pending`)

**bookings.Booking**
- `customer` FK(User), `provider` FK(Provider), `service` FK(Service) — hammasi `PROTECT`
- `start_at`, `end_at` (UTC); CHECK `start_at < end_at`
- `status`: `pending | confirmed | cancelled | completed`
- Snapshot: `service_name`, `duration_minutes`, `price` — xizmat keyin o'zgarsa tarix buzilmaydi
- `customer_note` (max 500), `internal_note` (admin/provider)
- `cancelled_at`, `cancelled_by` FK(User, null), `cancel_reason`
- `idempotency_key` (max 64, null)
- **Constraints:**
  ```python
  ExclusionConstraint(
      name="no_overlap_per_provider",
      expressions=[
          (F("provider"), RangeOperators.EQUAL),
          (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
      ],
      condition=Q(status__in=["pending", "confirmed"]),
  )
  ExclusionConstraint(
      name="no_overlap_per_customer",
      expressions=[
          (F("customer"), RangeOperators.EQUAL),
          (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
      ],
      condition=Q(status__in=["pending", "confirmed"]),
  )
  UniqueConstraint(fields=["customer", "idempotency_key"],
                   condition=Q(idempotency_key__isnull=False),
                   name="uniq_idempotency_per_customer")
  ```
  Migration'da `BtreeGistExtension()` operatsiyasi birinchi bo'lsin. `RangeBoundary()` default `[)` — 10:00–10:30 va 10:30–11:00 kesishmaydi.
- **Indexlar:** (provider, start_at), (customer, -start_at), (status, start_at)

**bookings.BookingStatusHistory**
- `booking` FK, `from_status` (null), `to_status`, `changed_by` FK(User, null), `reason`, `created_at`
- Immutable (update/delete taqiqlangan — model darajasida)

### 4.3 Nega shunday (suhbat uchun)
- **UUID pk** — URL'da ketma-ket ID'ni sanab chiqishni oldini oladi.
- **Snapshot maydonlar** — narx/nom/davomiylik tarixi; `service` o'zgarsa eski bron o'zgarmaydi.
- **PROTECT** — bronli xizmat/xodimni o'chirib bo'lmaydi; faqat `is_active=False`.
- **Status history alohida jadval** — audit, "kim, qachon, nega"; `updated_at` bilan bilib bo'lmaydi.
- **UTC + `[)` range** — timezone va chegaraviy slotlar muammosini DB hal qiladi.

---

## 5. Biznes logika

### 5.1 Slot engine (`scheduling/slot_engine.py`, pure)

```
get_available_slots(*, service, provider, date_local, now, settings, rules, time_offs, busy_ranges) -> list[Slot]
```
1. `rules[weekday]` → shu kunning ish oynalari (xodim tz'ida) → UTC oraliqlarga aylantir.
2. Oynalardan `time_offs` ni ayir (interval subtraction).
3. Oynalardan `busy_ranges` (shu xodimning `pending|confirmed` bronlari `[start_at, end_at)`) ni ayir.
4. Har bir qolgan oyna ichida `start = oyna_boshi`, `start` **`slot_step` ga tekislangan** (mahalliy vaqtda 09:00, 09:15, …), `start + duration ≤ oyna_oxiri` bo'lsa slot; keyin `start += step`.
5. Filtrlar: `start ≥ now + min_lead_time`, `start ≤ now + max_advance_days`, `start` o'tmishda emas.
6. Natija: `[{start_at(UTC), end_at(UTC)}]`; API mijoz tz'iga aylantirib beradi.

`get_day_summary(from, to)` — sana chizig'i uchun har kunda nechta slot borligi (max 31 kun, undan ko'p → 400).

Davomiylik step'ga karrali bo'lmasa (45 daq, step 15): slot boshlanishlari 09:00, 09:15, 09:30…; 09:00–09:45 band bo'lsa keyingi mumkin bo'lgan boshlanish 09:45. 40 daqiqalik xizmatda 09:00–09:40 band → keyingi 09:45 (birinchi step chegarasi ≥ 09:40). Bu qoida EDGE_CASES.md'da yozilsin.

### 5.2 Bron yaratish — 3.3-bo'limdagi oqim. Qo'shimcha:
- "Tekshir" bosqichlari **slot engine'ni qayta chaqiradi** (`start_at in get_available_slots(...)`), alohida if-lar bilan takrorlamaydi — bitta haqiqat manbai.
- `select_for_update()` faqat `Provider` qatoriga (butun jadval emas). Sabab: turli xodimlarga bron parallel ketaveradi.
- `idempotency_key` bo'lsa va shu mijozda mavjud bo'lsa → mavjud bron, `200`, header `Idempotent-Replayed: true`. Kalit bir xil, payload boshqa → `409 IDEMPOTENCY_MISMATCH`.

### 5.3 Status state machine (`bookings/state_machine.py`)

| Dan | Ga | Kim | Shart |
|---|---|---|---|
| pending | confirmed | provider (o'ziniki), admin | `start_at` o'tmagan |
| pending | cancelled | customer (o'ziniki), provider, admin | mijoz: deadline qoidasi |
| confirmed | cancelled | customer (o'ziniki), provider, admin | mijoz: `now ≤ start_at − cancellation_deadline_hours`; xodim/admin: cheklovsiz, `reason` majburiy |
| confirmed | completed | provider, admin | `now ≥ start_at` |
| completed / cancelled | — | — | terminal; har qanday urinish → `409 INVALID_TRANSITION` |

Amalga oshirish: `TRANSITIONS: dict[(from, to) -> Guard]`; `transition_booking(booking_id, to_status, actor, reason)` ichida `Booking.objects.select_for_update().get()` (ikki admin bir vaqtda bosgan holat), guard tekshiruvi, `save(update_fields=[...])`, history yozuvi, `on_commit` notification. `auto_confirm=True` bo'lsa yaratishda darhol `confirmed` (history: `None→pending→confirmed` ikki yozuv).

Bonus management command: `expire_stale_bookings` — `pending` va `start_at < now` → `cancelled`, reason `expired`, changed_by `None`. Cron/scheduler'da (compose'da alohida `scheduler` service yoki `django-crontab` emas — oddiy `while true; sleep` bilan entrypoint, hujjatlansin).

### 5.4 Timezone
- DB va service qatlami: faqat aware UTC `datetime`.
- Availability rule mahalliy `time` — xodim tz (yo'q bo'lsa biznes tz)'da talqin qilinadi, har kun uchun UTC'ga alohida aylantiriladi (DST bor mamlakatlar uchun to'g'ri ishlaydi).
- API: `start_at` ISO 8601 **offset bilan** majburiy (`2026-10-01T09:00:00+05:00`); offsetsiz → `400`. Javobda `start_at` UTC (`Z`) + `start_at_local` so'rovdagi `tz` (default: user tz → biznes tz).
- UI: foydalanuvchi tz'i (profil) — sanalar `Asia/Tashkent` da ko'rsatiladi; brauzer tz farq qilsa ogohlantirish chizig'i.

### 5.5 Xizmat/xodim/availability o'zgarganda
- `Service.duration/price` o'zgarishi — faqat yangi bronlarga; eskisi snapshot bilan qoladi.
- `Service`/`Provider` deaktivatsiya — mavjud faol bronlar saqlanadi, admin UI ogohlantiradi: "N ta kelajak broni bor". Yangi bron qilib bo'lmaydi.
- `TimeOff` qo'shish yoki `AvailabilityRule` toraytirish **faol bron bilan kesishsa** → `409 CONFLICTS_WITH_BOOKINGS` + kesishgan bronlar ro'yxati. Admin avval bronlarni bekor qiladi (yoki boshqa xodimga o'tkazish — bonus). Avtomatik bekor qilish yo'q (ADR-005): mijoz bilan bog'lanmasdan bekor qilish yomon mahsulot.

---

## 6. API dizayni

Base: `/api/v1/`. Auth: `Authorization: Bearer <access>`. Content: JSON. OpenAPI: `/api/schema/`, Swagger: `/api/docs/`.

### 6.1 Endpointlar

| Method | Path | Kim | Vazifa |
|---|---|---|---|
| POST | `/auth/register` | anon | mijoz ro'yxati (email, password, full_name, phone?) |
| POST | `/auth/token` | anon | login → access + refresh |
| POST | `/auth/token/refresh` | anon | rotation, eski refresh blacklist |
| POST | `/auth/logout` | user | refresh blacklist |
| GET/PATCH | `/me` | user | profil, timezone |
| GET | `/services` | anon | faol xizmatlar (admin: `?include_inactive=1`) |
| GET | `/services/{id}` | anon | |
| POST/PATCH/DELETE | `/services[/{id}]` | admin | DELETE = deaktivatsiya |
| GET | `/providers?service={id}` | anon | faol xodimlar, ixtiyoriy xizmat bo'yicha filtr |
| POST/PATCH/DELETE | `/providers[/{id}]` | admin | |
| PUT | `/providers/{id}/services` | admin | xizmatlar ro'yxatini butunlay almashtirish |
| GET/PUT | `/providers/{id}/availability` | admin, provider (o'ziniki) | haftalik qoidalar — butun hafta bitta payload |
| GET/POST/DELETE | `/providers/{id}/time-off[/{toid}]` | admin, provider (o'ziniki) | |
| GET | `/availability/slots?service=&provider=&date=&tz=` | anon | bir kun slotlari |
| GET | `/availability/days?service=&provider=&from=&to=&tz=` | anon | kunlar bo'yicha slot soni (max 31 kun) |
| POST | `/bookings` | customer | yaratish; `Idempotency-Key` header ixtiyoriy |
| GET | `/bookings` | user | customer: o'ziniki; provider: o'ziniki; admin: hammasi. Filtr: `status`, `from`, `to`, `provider`, `service`, `upcoming=1` |
| GET | `/bookings/{id}` | egasi/provider/admin | + `history[]` |
| POST | `/bookings/{id}/confirm` | provider/admin | |
| POST | `/bookings/{id}/cancel` | customer/provider/admin | body: `{reason}` |
| POST | `/bookings/{id}/complete` | provider/admin | |
| GET | `/settings` | anon (public qism) / admin (to'liq) | timezone, step, lead time, deadline |
| PATCH | `/settings` | admin | |
| GET | `/bookings/{id}/ical` | egasi | bonus: `.ics` |

Status o'zgarishi uchun `PATCH /bookings/{id} {status}` emas, **alohida action endpointlar** — har birining o'z guard'i va body'si bor, OpenAPI'da aniq ko'rinadi (ADR-007).

### 6.2 Xato formati (RFC 9457 uslubida, hamma joyda bir xil)

```json
{
  "type": "https://navbat.uz/errors/slot-taken",
  "title": "Bu vaqt band",
  "status": 409,
  "code": "SLOT_TAKEN",
  "detail": "Tanlangan vaqt boshqa mijoz tomonidan band qilindi. Boshqa vaqtni tanlang.",
  "errors": {"start_at": ["..."]}
}
```
`errors` faqat `422 VALIDATION_ERROR` da. DRF `EXCEPTION_HANDLER` orqali `DomainError`, `ValidationError`, `NotAuthenticated`, `PermissionDenied`, `Throttled`, `IntegrityError(exclusion)` hammasi shu shaklga tushadi.

**Kodlar:** `VALIDATION_ERROR 422`, `SLOT_TAKEN 409`, `SLOT_UNAVAILABLE 422` (ish vaqtidan tashqari/time off), `IN_PAST 422`, `LEAD_TIME 422`, `TOO_FAR_AHEAD 422`, `STEP_MISALIGNED 422`, `PROVIDER_NOT_OFFERING_SERVICE 422`, `INACTIVE_RESOURCE 422`, `CUSTOMER_OVERLAP 409`, `INVALID_TRANSITION 409`, `CANCELLATION_DEADLINE_PASSED 422`, `CONFLICTS_WITH_BOOKINGS 409`, `IDEMPOTENCY_MISMATCH 409`, `RANGE_TOO_LARGE 400`, `NOT_FOUND 404`, `AUTH_REQUIRED 401`, `FORBIDDEN 403`, `THROTTLED 429`.

### 6.3 Boshqa qoidalar
- Pagination: cursor emas, `page`/`page_size` (default 20, max 100) — bron tarixi uchun yetarli.
- Mijoz boshqa mijozning bronini so'rasa → `404` (403 emas — mavjudligini oshkor qilmaslik).
- Throttle: anon `60/min`, user `120/min`, `POST /bookings` `10/min` (user), `POST /auth/token` `10/min` (IP).
- Vaqt maydonlari doim ISO 8601. `date` = `YYYY-MM-DD` (mijoz tz'ida kun).
- Versioning URL'da (`/v1/`); breaking o'zgarish → `/v2/`.

### 6.4 Namuna

`GET /api/v1/availability/slots?service=…&provider=…&date=2026-10-01&tz=Asia/Tashkent`
```json
{
  "date": "2026-10-01",
  "timezone": "Asia/Tashkent",
  "service": {"id": "…", "name": "Soch olish", "duration_minutes": 30, "price": "60000.00"},
  "provider": {"id": "…", "name": "Sardor"},
  "slots": [
    {"start_at": "2026-10-01T04:00:00Z", "end_at": "2026-10-01T04:30:00Z", "start_local": "09:00", "end_local": "09:30"},
    {"start_at": "2026-10-01T04:15:00Z", "end_at": "2026-10-01T04:45:00Z", "start_local": "09:15", "end_local": "09:45"}
  ]
}
```

`POST /api/v1/bookings` → `201`
```json
{
  "id": "…", "status": "pending",
  "service": {"id": "…", "name": "Soch olish"}, "provider": {"id": "…", "name": "Sardor"},
  "start_at": "2026-10-01T04:00:00Z", "end_at": "2026-10-01T04:30:00Z",
  "start_at_local": "2026-10-01T09:00:00+05:00", "price": "60000.00", "currency": "UZS",
  "customer_note": "…", "can_cancel_until": "2026-09-30T04:00:00Z",
  "history": [{"from": null, "to": "pending", "by": "customer", "at": "…"}]
}
```

---

## 7. Validation (qatlam bo'yicha)

**Serializer/Form (shakl):** majburiy maydonlar, tiplar, uzunliklar (`name ≤ 100`, `note ≤ 500`), email format, telefon `^\+998\d{9}$` (yoki bo'sh), `price ≥ 0` va 2 kasr, `duration 5..480 % 5`, `weekday 0..6`, `start_time < end_time`, `tz` IANA ro'yxatida, `date` haqiqiy sana, `start_at` offset bilan, password: Django validatorlari (min 8, oddiy emas).

**Service (qoida):** slot mavjudligi, lead time, max advance, step, xizmat–xodim moslik, faollik, kesishish, state machine guard'lari, cancellation deadline, availability rule'lar o'zaro kesishmasligi, time off ↔ bron konflikti, sana oralig'i ≤ 31 kun.

**DB (kafolat):** exclusion ×2, unique'lar, CHECK'lar, PROTECT.

Bir xato bir marta ko'rsatiladi — shakl xatosi service'ga yetmaydi, service xatosi DB'ga yetmaydi (DB xatosi = bug yoki poyga).

---

## 8. Edge case'lar (EDGE_CASES.md ga shu jadval kengaytirilib kiradi; har biriga test)

| # | Holat | Kutilgan natija | Qanday hal qilinadi |
|---|---|---|---|
| 1 | Ikki mijoz **bir vaqtda** bir slotni bron qiladi | Biri `201`, ikkinchisi `409 SLOT_TAKEN`; DB'da bitta bron | `select_for_update(provider)` + exclusion constraint. Concurrency test: 10 thread, `TransactionTestCase`, aynan 1 ta muvaffaqiyat |
| 2 | Mijoz tugmani **ikki marta bosdi** / tarmoq retry | Bitta bron; ikkinchi javob `200` + `Idempotent-Replayed` | `Idempotency-Key`; UI tugmani loading holatiga o'tkazadi |
| 3 | Idempotency key bir xil, payload boshqa | `409 IDEMPOTENCY_MISMATCH` | payload hash solishtirish |
| 4 | Slot **o'tmishda** (yoki "hozir") | `422 IN_PAST` | `now` faqat serverda; UI o'tgan vaqtni ko'rsatmaydi |
| 5 | Slot lead time ichida (masalan 30 daq keyin, limit 60) | `422 LEAD_TIME` | |
| 6 | 31 kundan keyin (limit 30) | `422 TOO_FAR_AHEAD` | |
| 7 | Slot ish vaqtining oxiriga **sig'maydi** (17:45, xizmat 30 daq, oyna 18:00 gacha) | Slot ko'rsatilmaydi; to'g'ridan-to'g'ri so'rov → `422 SLOT_UNAVAILABLE` | engine `start + duration ≤ window_end` |
| 8 | Slot step'ga mos emas (10:07) | `422 STEP_MISALIGNED` | |
| 9 | Xodim bu xizmatni ko'rsatmaydi | `422 PROVIDER_NOT_OFFERING_SERVICE` | |
| 10 | Xizmat yoki xodim `is_active=False` | `422 INACTIVE_RESOURCE`; ro'yxatlarda ko'rinmaydi | |
| 11 | Xizmat `duration` o'zgartirildi | Eski bronlar o'zgarmaydi; yangi slotlar yangi davomiylikda | snapshot |
| 12 | Narx o'zgardi | Eski bronda eski narx | snapshot |
| 13 | Admin **time off** qo'shdi, u yerda faol bron bor | `409 CONFLICTS_WITH_BOOKINGS` + ro'yxat | avval bekor qilish kerak |
| 14 | Availability rule toraytirildi, faol bron tashqarida qoldi | `409 CONFLICTS_WITH_BOOKINGS` | |
| 15 | Bir kunda ikki rule kesishadi (09–14, 13–18) | `422 VALIDATION_ERROR` | service tekshiruvi |
| 16 | Rule yarim tundan o'tadi (22:00–02:00) | `422` — v1'da qo'llab-quvvatlanmaydi, hujjatlangan | ADR-004 |
| 17 | Mijoz boshqa timezone'da (Dubay, +04:00) | Slotlar mijoz tz'ida ko'rsatiladi; DB UTC; bron to'g'ri joyga tushadi | `tz` param + profil |
| 18 | DST bor mamlakat xodimi (bonus test) | Har kun uchun alohida UTC konversiya | `zoneinfo` |
| 19 | Mijoz deadline'dan **keyin** bekor qilmoqchi | `422 CANCELLATION_DEADLINE_PASSED`; UI: "Bekor qilish uchun +998… ga qo'ng'iroq qiling" | policy |
| 20 | `cancelled` yoki `completed` bronni yana o'zgartirish | `409 INVALID_TRANSITION` | state machine |
| 21 | Uchrashuv boshlanmasdan `completed` | `409 INVALID_TRANSITION` (guard `now ≥ start_at`) | |
| 22 | `start_at` o'tib ketgan `pending` bronni confirm qilish | `409` | + `expire_stale_bookings` |
| 23 | Ikki admin bir vaqtda bitta bronni o'zgartiradi | Ikkinchisi joriy holatga qarab `409` yoki no-op | `select_for_update(booking)` |
| 24 | Mijozning o'zi kesishuvchi ikkinchi bron qiladi (boshqa xodimga) | `409 CUSTOMER_OVERLAP` | exclusion per customer |
| 25 | Xodim deaktivatsiya qilinmoqda, kelajak bronlari bor | Ogohlantirish + ro'yxat; deaktivatsiya mumkin, bronlar saqlanadi, yangi bron yo'q | |
| 26 | Mijoz boshqa mijoz bronini ochmoqchi | `404` | enumeration'dan himoya |
| 27 | Slot so'rovi 90 kunlik oraliq | `400 RANGE_TOO_LARGE` | max 31 |
| 28 | Noto'g'ri `tz` (`Asia/Toshkent`) | `422` | IANA ro'yxati |
| 29 | Email yuborish xato berdi | Bron saqlanadi, xato loglanadi | `on_commit` + try/except |
| 30 | Refresh token qayta ishlatildi | `401`, oila blacklist | simplejwt rotation |
| 31 | Bir IP'dan 100 ta bron urinishi | `429` | throttle |
| 32 | `customer_note` ichida `<script>` | Eskeyplanadi, saqlanadi | Django auto-escape; API'da ham xom qaytadi, UI eskeyplaydi |
| 33 | Uzun o'zbek ismi (40+ belgi) | UI'da ellipsis / 2 qator; DB limit 120 | |
| 34 | Xizmat davomiyligi 45, step 15, 09:00 band | Keyingi slot 09:45 | 5.1 qoidasi |
| 35 | Provider `user` bilan bog'lanmagan | Faqat admin boshqaradi; provider endpointlari `403` | |
| 36 | `auto_confirm=True` | Yaratishda `confirmed`; history 2 yozuv | |
| 37 | Bron yaratish tranzaksiyasi o'rtasida DB uzildi | Hech narsa saqlanmaydi, `503`; email yuborilmaydi | atomic + on_commit |
| 38 | Sana chegarasi: mijoz tz'ida "1-oktabr" xodim tz'ida 30-sentabr kechqurunga tushadi | `date` mijoz tz'ida talqin qilinadi, engine UTC oraliq bilan ishlaydi | |

---

## 9. Auth va ruxsatlar

- Ro'yxatdan o'tish faqat `customer`. `provider`/`admin` ni admin yaratadi (bonus: taklif havolasi).
- Session (UI) va JWT (API) — ikkalasi bir `User` jadvali. Django admin (`/django-admin/`) faqat superuser uchun, biznes UI `/dashboard/` da.
- Permission klasslari: `IsAdmin`, `IsProvider`, `IsOwnerOrAdmin`, `IsProviderOfBookingOrAdmin`. Har endpoint jadvalda (6.1) ko'rsatilgan kim'ga mos test.
- Parol: Django validatorlari; login throttle; `SECURE_*` prod sozlamalari; CSRF UI'da yoqiq; CORS faqat kerak bo'lsa (`django-cors-headers`, whitelist).

---

## 10. UI/UX

### 10.1 Prinsiplar
Sahifaning **bitta** vazifasi. Mobile-first (360px birinchi). Bitta ekranda bitta primary tugma. Har interaktiv elementda default/hover/focus-visible/active/disabled/loading holati. Empty/loading/error holatlari oldindan. Matn o'zbekcha, fe'l + ob'ekt ("Bronni tasdiqlash", "Submit" emas). Apostrof `ʻ` (U+02BB) bitta konstantada. Emoji ikonka o'rnida ishlatilmaydi — **Lucide** SVG.

**Signature element:** slot picker — gorizontal sana chizig'i (7 kun, har kunda "N bo'sh" mikro-yorliq) + vaqt chiplari 3 guruhda (Ertalab / Kunduzi / Kechqurun). Qolgan hamma narsa jim va toza.

### 10.2 Design tokenlar (`static/css/tokens.css` + Tailwind config)

```css
:root {
  --bg:#FFFFFF; --bg-subtle:#F7F8FA; --surface:#FFFFFF;
  --border:#E5E7EB; --border-strong:#D1D5DB;
  --text:#0F172A; --text-muted:#64748B; --text-subtle:#94A3B8;
  --primary:#2563EB; --primary-hover:#1D4ED8; --primary-soft:#EFF6FF;
  --success:#16A34A; --success-soft:#F0FDF4;
  --warning:#D97706; --warning-soft:#FFFBEB;
  --danger:#DC2626;  --danger-soft:#FEF2F2;
  --focus-ring:#2563EB;
  --radius-sm:6px; --radius-md:10px; --radius-lg:16px;
  --shadow-sm:0 1px 2px rgb(0 0 0/.04),0 1px 3px rgb(0 0 0/.06);
  --shadow-md:0 2px 4px rgb(0 0 0/.04),0 4px 12px rgb(0 0 0/.08);
  --dur-fast:150ms; --dur-base:200ms; --dur-slow:300ms;
  --ease-out:cubic-bezier(.16,1,.3,1);
}
```
- Shrift: **Inter** (Lotin + Kirill + `ʻ`), weight 400/500/600. Body 16px (mobil inputda ham 16px). Raqamlar `tabular-nums`.
- Spacing 4pt grid: 4/8/12/16/24/32/48/64. Radius filosofiyasi bitta: `md` (tugma, card, input), `lg` (modal), `full` (chip, avatar).
- Status ranglari: `pending` → warning-soft/warning, `confirmed` → primary-soft/primary, `completed` → success-soft/success, `cancelled` → bg-subtle/text-muted. Badge = rang + ikonka + matn (faqat rang emas).
- Dark mode v1'da yo'q (tokenlar tayyor, keyin bir joyda almashadi).
- `prefers-reduced-motion` — majburiy global qoida. Animatsiya faqat `transform`/`opacity`, ≤ 300ms.

### 10.3 Sahifalar

**Ochiq / mijoz** (`web`):
| Route | Vazifa |
|---|---|
| `/` | Xizmatlar ro'yxati (card: nom, davomiylik, narx `60 000 soʻm`, "Vaqt tanlash" tugmasi). Navbar: logo, "Bronlarim", til/profil |
| `/book/<service_slug>/` | 4-qadamli stepper: 1 Xodim → 2 Sana va vaqt → 3 Tasdiqlash → 4 Natija |
| `/bookings/` | Bronlarim: tabs "Kelgusi / O'tgan / Bekor qilingan", card ro'yxati |
| `/bookings/<id>/` | Tafsilot + status timeline + "Bekor qilish" (deadline'gacha) |
| `/login/`, `/register/`, `/profile/` | |

**Dashboard** (`/dashboard/…`, provider + admin; sidebar 240px, mobilda drawer):
| Route | Vazifa |
|---|---|
| `/dashboard/` | Bugun: xodimlar bo'yicha ustunli kun ko'rinishi (09:00–19:00 vaqt o'qi, bron bloklari xodim rangida); yuqorida 3 KPI (Bugun bronlar, Kutilmoqda, Bekor qilingan %) |
| `/dashboard/bookings/` | Jadval: filtr (status, xodim, sana oralig'i, qidiruv), qator: mijoz, xizmat, xodim, vaqt, status badge, amallar. Mobilda card. Filtrlar URL'da |
| `/dashboard/bookings/<id>/` | Tafsilot, Confirm / Complete / Cancel (reason bilan, tasdiq modali) |
| `/dashboard/services/` | Jadval + yaratish/tahrirlash formasi (modal 640px / mobilda bottom sheet) |
| `/dashboard/providers/` | Ro'yxat, xizmatlar checkbox'lari |
| `/dashboard/providers/<id>/availability/` | Haftalik grid: 7 kun × oraliqlar; "+ oraliq qo'shish"; time off ro'yxati |
| `/dashboard/settings/` | Timezone, step, lead time, max advance, deadline, auto-confirm |

### 10.4 Bron oqimi (asosiy ekran) — wireframe, mobil

```
┌──────────────────────────────┐
│ ← Soch olish · 30 daq · 60 000 soʻm │   sticky sarlavha, xizmat konteksti
├──────────────────────────────┤
│ ● Xodim  ○ Vaqt  ○ Tasdiq    │   stepper (3 ko'rinadigan qadam)
├──────────────────────────────┤
│ [Istalgan xodim] (bonus)     │
│ ┌────┐ Sardor      4.9★      │   card: avatar monogram, ism, bio 1 qator
│ │ SA │ 12 yil tajriba        │   butun card klikli, tanlangan → primary border
│ └────┘                        │
│ ┌────┐ Jasur                 │
│ …                            │
├──────────────────────────────┤
│ [ Davom etish ]  (primary)   │   sticky pastki bar
└──────────────────────────────┘

Vaqt qadami:
┌──────────────────────────────┐
│ ‹  Du 29  Se 30  Ch 1  Pa 2 › │   sana chizig'i, har kunda "6 bo'sh" / "—"
│      ─         ─    ●         │   tanlangan kun ostida nuqta
├──────────────────────────────┤
│ ERTALAB                       │   eyebrow 12px uppercase muted
│ [09:00] [09:15] [09:30] [10:00]│   chip: 44px balandlik, tanlangan = primary fon
│ KUNDUZI                       │
│ [13:00] [13:30] …             │
│ KECHQURUN                     │
│ Bu vaqtda bo'sh joy yo'q      │   guruh bo'sh bo'lsa muted matn
├──────────────────────────────┤
│ Sardor · Ch, 1-okt · 09:30    │   tanlov xulosasi
│ [ Bronni tasdiqlash ]         │
└──────────────────────────────┘
```
- Kun tanlanganda slotlar HTMX bilan yangilanadi (`hx-get` → partial), skeleton 300ms'dan keyin.
- Slot bo'sh kun: "Bu kunda bo'sh vaqt yo'q. Keyingi bo'sh kun: Ju, 3-okt →" (keyingi qadam bilan empty state).
- `409 SLOT_TAKEN` kelsa: xato toast ("Bu vaqt hozirgina band qilindi") + slotlar avtomatik qayta yuklanadi, tanlov o'chadi.
- Tasdiqlash qadami: xulosa card + note textarea (500) + ishonch mikromatni: "Bekor qilish 24 soat oldin bepul • SMS/emailda eslatma".
- Natija: katta ✓ ikonka, "Bron qabul qilindi — tasdiqlashni kuting" (pending) yoki "Bron tasdiqlandi", "Bronlarim"ga havola, `.ics` yuklash (bonus).

### 10.5 Komponentlar (bitta `components/` partial to'plami)
`button` (primary/secondary/ghost/destructive; sm/md/lg; loading), `input` (label → input → helper/error), `select`, `textarea`, `card`, `badge` (status), `modal`/`bottom-sheet` (focus trap, Esc, body scroll lock), `toast` (`role="status"`, xato toasti avtomatik yopilmaydi), `table` + `mobile card list`, `empty-state`, `skeleton`, `stepper`, `date-strip`, `slot-chip`, `sidebar`, `topbar`.

### 10.6 Accessibility (topshirishdan oldin tekshiriladi)
Semantik HTML; `label for`; `:focus-visible` ring; kontrast 4.5:1; klaviatura bilan butun bron oqimi; modal `role="dialog" aria-modal`; `aria-live` toast; touch ≥ 44px; `<html lang="uz">`; 200% zoom'da buzilmaydi; 360px va 1440px'da tekshirilgan.

---

## 11. Testlar

`pytest` + `pytest-django`, `DATABASES` test uchun ham Postgres (Docker). Maqsad: service va engine qatlami ≥ 90%, umumiy ≥ 80%.

| Katalog | Nima |
|---|---|
| `tests/unit/test_slot_engine.py` | oynalar, time off ayirish, band oraliq ayirish, step tekislash, davomiylik sig'ishi, lead time, max advance, tz konversiya, 45/15 holati, chegaralar `[)` |
| `tests/unit/test_state_machine.py` | har bir ruxsat etilgan/etilmagan o'tish, guard'lar, kim qila oladi |
| `tests/unit/test_time_utils.py` | mahalliy→UTC, sana chegarasi, IANA validatsiya |
| `tests/api/test_auth.py` | register, login, refresh rotation, reuse → 401, throttle |
| `tests/api/test_services.py`, `test_providers.py`, `test_availability.py` | CRUD, permission, rule kesishishi, time off konflikti (`409` + ro'yxat) |
| `tests/api/test_bookings.py` | yaratish (happy), 8-bo'limdagi har bir case → alohida test nomi `test_edge_XX_...` |
| `tests/api/test_permissions.py` | mijoz boshqa bronni ko'rmaydi (404), provider faqat o'ziniki |
| `tests/concurrency/test_double_booking.py` | `TransactionTestCase`; 10 thread `threading.Barrier` bilan bir vaqtda `POST /bookings`; assert: 1×201, 9×409, DB'da 1 bron. Alohida: ORM'ni aylanib `Booking.objects.create` bilan kesishuvchi qator → `IntegrityError` (constraint ishlaydi) |
| `tests/web/test_booking_flow.py` | Django test client bilan 4 qadam, HTMX partial, 409 holati |
| `tests/test_architecture.py` | `grep`: `bookings/services.py`dan tashqari joyda `.status =` yozuvi yo'q |

Factories: `UserFactory(role)`, `ServiceFactory`, `ProviderFactory(with_services)`, `AvailabilityRuleFactory`, `BookingFactory`. `freezegun` bilan `now` qotiriladi.

---

## 12. Docker, CI, deploy

- `docker/Dockerfile` — multi-stage (builder: deps + tailwind build; runtime: slim, non-root). `entrypoint.sh`: `migrate` → `collectstatic` → gunicorn (prod) yoki `runserver` (dev, volume bilan).
- `docker-compose.yml` (dev): `db` (postgres:16, healthcheck), `web` (volume `.:/app`, `env_file .env`). `docker-compose.prod.yml`: `web` + `db` + `scheduler` (expire command loop) + ixtiyoriy `caddy`.
- `.env.example`: `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `EMAIL_*`, `DEFAULT_TZ`.
- `manage.py seed_demo` — admin, 3 xodim (biri user'li), 5 xizmat, haftalik rule'lar, 1 time off, ~25 bron (hamma statusdan, o'tgan va kelgusi). README'da demo login'lar.
- CI (`.github/workflows/ci.yml`): `ruff check` + `ruff format --check` → `pytest` (postgres service container) → Docker build. Badge README'da.
- Deploy: **Railway yoki Render** (Dockerfile'dan, managed Postgres) — eng tez demo URL. Muqobil: VPS + compose.prod + Caddy (README'da qadamlar). Health endpoint `/healthz` (DB ping).

PowerShell buyruqlari README'da: `docker compose up -d db`, `python -m venv .venv; .\.venv\Scripts\Activate.ps1`, `pip install -r requirements/dev.txt`, `python manage.py migrate`, `python manage.py seed_demo`, `python manage.py runserver`, `pytest`.

---

## 13. Hujjatlar (deliverable)

### 13.1 README.md
Nima, skrinshot/GIF, demo URL + demo loginlar, tez boshlash (Docker va lokal), `.env`, testni ishga tushirish, API docs havolasi, loyiha tuzilishi qisqa, hujjatlarga havolalar, litsenziya.

### 13.2 docs/ARCHITECTURE.md
Qatlamlar diagrammasi, so'rov oqimi (3.3), DB sxemasi va constraint'lar izohi, slot engine algoritmi, state machine jadvali, timezone strategiyasi, auth, xato formati, "nega Django/DRF/Postgres/HTMX", trade-off'lar, "o'sganda nimani qayta ko'rib chiqaman" (queue, cache, read replica, multi-tenant).

### 13.3 docs/EDGE_CASES.md
8-bo'lim jadvali + har biriga: qanday sinash mumkin (curl namuna yoki test nomi).

### 13.4 docs/decisions/ (minimal)
`ADR-001` single-tenant ko'lami · `ADR-002` HTMX vs SPA · `ADR-003` double-booking: lock + exclusion · `ADR-004` availability yarim tundan o'tmaydi · `ADR-005` availability o'zgarganda bronlarni avtomatik bekor qilmaslik · `ADR-006` email queue'siz (on_commit) · `ADR-007` status action endpointlari · `ADR-008` UUID pk va snapshot maydonlar · `ADR-009` UTC saqlash, offset majburiy.

### 13.5 docs/AI_USAGE.md
Bosqich bo'yicha: prompt qisqacha → nima generatsiya bo'ldi → qanday tekshirildi → nima o'zgartirildi → AI xatolari (bo'lsa). Oxirida: "Nimani o'zim yozdim / o'zgartirdim" ro'yxati.

### 13.6 Suhbat uchun javob skeletlari (docs/INTERVIEW_NOTES.md, qisqa)
- Double booking: 3 qatlam (UI disable → lock → constraint), nega faqat bittasi yetmaydi.
- Nega service qatlami: bitta yozish nuqtasi, ikki interfeys, testlanadi.
- Nega exclusion `[)`: 10:30 chegarasi.
- Nega snapshot: tarix o'zgarmaydi.
- Nega 404 (403 emas) begona bronda.
- Timezone: DB UTC, rule mahalliy, konversiya kun-ba-kun.
- O'sganda: slot cache (Redis, provider-day kalit, bron yozilganda invalidatsiya), email queue, read replica, multi-tenant `business_id`.

---

## 14. Bosqichlar va Git rejasi

Har bosqich oxirida: `pytest` yashil, `ruff` toza, `docs/AI_USAGE.md` yangilangan, commit'lar push qilingan.

| # | Bosqich | Commit'lar (namuna) | Tugallangan hisoblanadi |
|---|---|---|---|
| 0 | Skeleton | `chore: init django project, settings split, ruff, pytest` · `chore: docker compose with postgres` · `docs: add TASK.md, README skeleton, ADR-001/002` | `docker compose up` ishlaydi, `pytest` bo'sh o'tadi, CI yashil |
| 1 | Accounts + auth | `feat(accounts): custom user with email login and roles` · `feat(api): jwt auth endpoints with rotation` · `test(api): auth flows and throttling` | register/login/refresh testlari |
| 2 | Catalog + providers | `feat(catalog): service model with constraints` · `feat(providers): provider and provider-service` · `feat(api): services/providers endpoints + permissions` · `test: ...` | CRUD + permission testlari, soft delete |
| 3 | Scheduling | `feat(scheduling): availability rules, time off, business settings` · `feat(api): availability and time-off endpoints` · `test: rule overlap validation` | rule/time off testlari |
| 4 | Slot engine | `feat(scheduling): pure slot engine` · `test(unit): slot engine edge cases` · `feat(api): slots and days endpoints` | 5.1 dagi har qoida uchun test |
| 5 | Booking create + concurrency | `feat(bookings): booking model with exclusion constraints` · `feat(bookings): create_booking service with provider lock` · `feat(api): POST /bookings with idempotency` · `test(concurrency): parallel booking yields one winner` · `docs: ADR-003` | concurrency test yashil |
| 6 | State machine | `feat(bookings): state machine and transition service` · `feat(bookings): status history` · `feat(api): confirm/cancel/complete actions` · `feat(bookings): cancellation policy` · `test: transitions matrix` | 5.3 jadvalidagi har katak test |
| 7 | API polish | `feat(api): problem-details error handler` · `feat(api): filters, pagination, throttles` · `feat(api): openapi schema and swagger` · `feat(scheduling): conflict check on time off / rule change` | 6.2 format, Swagger ochiladi, 8-jadval testlari to'liq |
| 8 | UI — mijoz | `feat(web): base layout, tokens, components` · `feat(web): services page and booking stepper` · `feat(web): my bookings and detail with timeline` · `feat(web): auth pages` · `test(web): booking flow` | 360px + 1440px, klaviatura, holatlar |
| 9 | UI — dashboard | `feat(web): dashboard today view` · `feat(web): bookings table with filters` · `feat(web): services, providers, availability editor` · `feat(web): settings` | admin butun boshqaruvni UI'da qila oladi |
| 10 | Notifications | `feat(notifications): email on create/confirm/cancel via on_commit` · `test: email failure does not roll back booking` | console backend'da ko'rinadi |
| 11 | Ops | `chore: production dockerfile and compose` · `feat: healthz, seed_demo, expire_stale_bookings` · `ci: github actions` · `docs: deploy guide` | deploy qilingan URL |
| 12 | Hujjat va yakun | `docs: architecture, edge cases, ai usage, interview notes` · `docs: readme with demo credentials and screenshots` · `chore: final lint/test pass` | 15-bo'lim checklist to'liq |

Bonuslar (1-bo'limdagi tartibda) 12-bosqichdan keyin, har biri alohida `feat(bonus): ...` commit.

---

## 15. Definition of Done

- [ ] Barcha minimum talablar ishlaydi (API + UI)
- [ ] Concurrency testi bor va yashil; exclusion constraint migration'da
- [ ] 8-bo'limdagi har bir case uchun test nomi bor
- [ ] Xato formati hamma joyda bir xil, kodlar hujjatlangan
- [ ] Swagger `/api/docs/` ochiladi, har endpoint tavsifli
- [ ] `docker compose up` → seed → UI ishlaydi (yangi mashinada README bo'yicha)
- [ ] CI yashil, ruff toza
- [ ] README, ARCHITECTURE, EDGE_CASES, AI_USAGE, ADR-001…009, INTERVIEW_NOTES mavjud
- [ ] Git tarixi 14-bo'lim tartibida, mazmunli commit xabarlari
- [ ] Public GitHub repo + demo URL + demo loginlar
- [ ] UI: 360px va 1440px, klaviatura, kontrast, holatlar, placeholder yo'q
- [ ] Hech qanday secret repo'da yo'q (`.env` ignore, `.env.example` bor)

---

## 16. Claude Code'ga birinchi xabar (nusxa ko'chiring)

```
TASK.md faylini to'liq o'qi. Bu — Django'da appointment booking system uchun texnik topshiriq.
Ish qoidalari 0-bo'limda, bosqichlar 14-bo'limda.

Boshlashdan oldin:
1) CLAUDE.md yarat: loyiha nomi, stack, papka tuzilishi (3.2), asosiy qoidalar (0-bo'lim va 3.1),
   PowerShell buyruqlari, "status faqat bookings/services.py da o'zgaradi" qoidasi.
2) docs/AI_USAGE.md ni bosh sarlavhalar bilan yarat.
3) 0-bosqich (Skeleton) rejasini 5 qatorda ko'rsat va boshla.

Har bosqichdan keyin to'xta, hisobot ber, men "davom et" deganimdan keyin keyingi bosqichga o't.
Test o'tmasa keyingi bosqichga o'tma. Placeholder qoldirma.
```

Keyingi bosqichlar uchun: `davom et — N-bosqich`. UI bosqichidan oldin: `10-bo'limni va frontend-uiux-skill'ni qayta o'qi, keyin 8-bosqich`.
