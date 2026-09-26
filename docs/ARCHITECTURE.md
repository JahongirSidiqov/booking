# Arxitektura

Navbat — bitta Django loyihasi: REST API (DRF, JWT) va HTML UI (templates + HTMX, session) bir xil service qatlamini chaqiradi. PostgreSQL double booking'ni DB darajasida taqiqlaydi. Qarorlarning to'liq asoslari — [decisions/](decisions/) (ADR-001…009).

## 1. Qatlamlar

```
                HTTP
      ┌──────────┴───────────┐
  apps/api/v1              apps/web
  DRF views + serializers  Django views + forms + templates (HTMX, Alpine)
  (JWT, JSON, OpenAPI)     (session, HTML)
      └──────────┬───────────┘      shakl validatsiyasi: tiplar, uzunlik, offset, IANA zona
                 ▼
  <app>/services.py     yozish: biznes qoidalari, tranzaksiya, lock, state machine,
                        on_commit email — YAGONA yozish nuqtasi
  <app>/selectors.py    o'qish: queryset'lar, ko'rinish qoidalari (kim nimani ko'radi)
  scheduling/slot_engine.py   sof funksiyalar (DB'siz, soatsiz) — bo'sh slotlar
  bookings/state_machine.py   sof funksiyalar — o'tishlar jadvali va guard'lar
                 ▼
  <app>/models.py       maydonlar, CHECK / UNIQUE / EXCLUDE constraint'lar, indekslar
                 ▼
  PostgreSQL 16 (btree_gist)
```

| App | Mas'uliyat |
|---|---|
| `common` | `BaseModel` (UUID, created/updated), `DomainError`, RFC 9457 xato handler'i, `/healthz`, `seed_demo` |
| `accounts` | `User` (email login, rol, timezone), ro'yxatdan o'tish, JWT token oilasi |
| `catalog` | `Service` (snapshot qilinadigan narx/davomiylik, soft delete) |
| `providers` | `Provider`, `ProviderService` |
| `scheduling` | `AvailabilityRule`, `TimeOff`, `BusinessSettings` (singleton), **slot engine** |
| `bookings` | `Booking`, `BookingStatusHistory`, **state machine**, `create_booking`, `transition_booking`, `expire_stale_bookings` |
| `notifications` | email yuboruvchilar (`on_commit`) |
| `api` | v1 view'lar, serializer'lar, ruxsatlar, pagination, OpenAPI |
| `web` | mijoz sahifalari, bron oqimi, dashboard |

**Qoidalar (testlar bilan himoyalangan):**
- `Booking.status` faqat `apps/bookings/services.py` da o'zgaradi: `tests/test_architecture.py` butun `apps/` ni grep qiladi, `Booking.save()` service belgisisiz status o'zgarishini rad etadi, Django admin'da bron faqat o'qish uchun.
- View'da biznes mantiq yo'q: API va UI bir xil `create_booking` / `transition_booking` / `replace_availability` ni chaqiradi — bitta qoida bir marta yozilgan.
- Slot engine va state machine — DB'siz sof funksiyalar; `now` parametr sifatida keladi, testlarda soat qotiriladi.

## 2. Bron yaratish oqimi

```
POST /api/v1/bookings  {service_id, provider_id, start_at(+offset), note}  [Idempotency-Key]
  │  (yoki /book/<slug>/confirm/ formasi — xuddi shu service)
  ▼ serializer: majburiy maydonlar, offset majburiy, note ≤ 500, kalit formati
  ▼ services.create_booking
     BEGIN
     1. SELECT … FROM provider WHERE id = … FOR UPDATE        ← shu xodimga so'rovlar navbatga turadi
     2. idempotency: shu mijozda shu kalit bor? → payload hash teng → 200 replay / farq → 409
     3. bookable_pair: topildi? faolmi? xodim bu xizmatni ko'rsatadimi?   → 404 / 422
     4. slot_engine.slot_rejection(start_at, rules, time_offs, busy)      → IN_PAST / LEAD_TIME /
        (hukmni get_available_slots o'zi chiqaradi — ro'yxat va tekshiruv bitta funksiya)
                                                                            TOO_FAR_AHEAD / STEP_MISALIGNED /
                                                                            SLOT_UNAVAILABLE / SLOT_TAKEN
     5. mijozning o'zida kesishuvchi faol bron?                            → 409 CUSTOMER_OVERLAP
     6. INSERT booking (snapshot: service_name, duration, price)          ← EXCLUDE constraint'lar — oxirgi qalqon
     7. INSERT history (None → pending); auto_confirm bo'lsa → confirmed (2-yozuv)
     8. on_commit(send booking_created)
     COMMIT
  ▼ IntegrityError(no_overlap_*) → 409 SLOT_TAKEN / CUSTOMER_OVERLAP;  OperationalError → 503
  ▼ 201 + bron JSON (UTC `Z` + so'rovchining zonasidagi `*_local`)
```

Nega lock **va** constraint (ADR-003): lock poygani tartibga soladi — ikkinchi so'rov kutadi, keyin g'olibning qatorini ko'rib odatdagi `409` oladi. Constraint esa lock'ni chetlab o'tgan har qanday yo'lni (admin, shell, kelajakdagi bug, turli xodimlarga bir vaqtda yozilayotgan bitta mijoz) to'xtatadi. O'lchov: 10 parallel so'rovda lock bilan 0 ta yutqazuvchi constraint'gacha yetdi, lock'siz 1–2 tasi yetdi va faqat constraint to'xtatdi.

## 3. Ma'lumotlar bazasi

```
User 1───0..1 Provider ──< ProviderService >── Service
 │              ├──< AvailabilityRule (weekday, start_time, end_time — xodimning mahalliy vaqti)
 │              ├──< TimeOff (start_at, end_at — UTC)
 └──< Booking >─┴───────────────────────────────┘
        └──< BookingStatusHistory (append-only)
BusinessSettings (pk = 1)
```

| Jadval | Muhim constraint'lar |
|---|---|
| `accounts_user` | `email` unique + `CHECK email = lower(email)`, `CHECK role IN (…)` |
| `catalog_service` | `CHECK 5 ≤ duration ≤ 480`, `CHECK duration % 5 = 0`, `CHECK price ≥ 0`, `slug` unique |
| `providers_provider` | `CHECK color ~ '^#[0-9A-Fa-f]{6}$'`; `user` OneToOne |
| `providers_providerservice` | `UNIQUE (provider, service)` |
| `scheduling_availabilityrule` | `CHECK start_time < end_time` (yarim tundan o'tmaydi — ADR-004), `CHECK weekday 0..6` |
| `scheduling_timeoff` | `CHECK start_at < end_at`, index `(provider, start_at)` |
| `scheduling_businesssettings` | `CHECK id = 1`, step ∈ {5,10,15,20,30,60}, chegaralar |
| `bookings_booking` | `EXCLUDE USING gist (provider WITH =, tstzrange(start_at, end_at, '[)') WITH &&) WHERE status IN ('pending','confirmed')`; xuddi shunday `customer` bo'yicha; `UNIQUE (customer, idempotency_key) WHERE key IS NOT NULL`; `CHECK start_at < end_at`; FK'lar `PROTECT`; indekslar `(provider, start_at)`, `(customer, -start_at)`, `(status, start_at)` |
| `bookings_bookingstatushistory` | update/delete model va queryset darajasida taqiqlangan |

- **UUID pk** — ID'larni sanab chiqib bo'lmaydi; begona bron baribir `404` (ADR-008).
- **Snapshot** — xizmat nomi/narxi/davomiyligi o'zgarsa eski bron o'zgarmaydi; `end_at` ham saqlangan, shuning uchun constraint oralig'i ham o'zgarmaydi.
- **Soft delete** — xizmat va xodim o'chirilmaydi, `is_active=False`; `DELETE` endpoint'i kelgusi bronlar ro'yxatini qaytaradi.
- **`[)`** — 10:00–10:30 va 10:30–11:00 kesishmaydi; bekor qilingan/bajarilgan bronlar constraint'dan chiqadi.

## 4. Slot engine (`scheduling/slot_engine.py`)

`get_available_slots(service, provider, date_local, now, settings, rules, time_offs, busy_ranges, tz)`:

1. Mijozning `date_local` kuni (`tz` zonasida) → UTC oraliq `[day_start, day_end)`.
2. Shu oraliqqa tegadigan **har bir xodim sanasi** uchun qoidalar xodim zonasida o'sha sananing UTC oynalariga aylantiriladi (DST uchun to'g'ri; mijoz kuni xodimning ikki sanasiga tushishi mumkin — edge #38).
3. Oynalardan time off, keyin band bronlar ayiriladi (`subtract`, yarim ochiq oraliqlar, birlashtirish bilan).
4. Har oynada boshlanish **xodimning mahalliy yarim tunidan step setkasiga** tekislanadi (`align_to_step`), `start + duration ≤ oyna oxiri` bo'lguncha `step` bilan yuriladi.
5. Filtr: mijoz kuni ichida, `start > now`, `start ≥ now + lead`, `start ≤ now + max_advance`.

`slot_rejection(start_at, …)` bron yaratishda rad sababini beradi, lekin hukmni shu `get_available_slots` chiqaradi (ro'yxatda ko'ringan slot — bron qilinadigan slot; test: `test_slot_rejection_agrees_with_listing_for_every_candidate`). `uncovered()` jadval toraytirilganda tashqarida qolgan bronlarni topadi. Tafsilotlar va misollar: [EDGE_CASES.md](EDGE_CASES.md#slot-boshlanishi-qanday-tanlanadi).

## 5. Holatlar (state machine)

```
pending ──confirm──▶ confirmed ──complete──▶ completed
   │                     │
   └──────cancel─────────┴──────▶ cancelled        (completed, cancelled — yakuniy)
```

| Dan → Ga | Kim | Shart |
|---|---|---|
| pending → confirmed | provider (o'ziniki), admin, system | uchrashuv boshlanmagan |
| pending → cancelled | customer (o'ziniki), provider, admin, system | mijoz: `now ≤ start − deadline`; xodim/admin: sabab majburiy |
| confirmed → cancelled | xuddi shunday | xuddi shunday |
| confirmed → completed | provider, admin | `now ≥ start` |

- Xato tartibi: bunday o'tish yo'q → `409 INVALID_TRANSITION`; rol mos emas → `403`; guard → `409`/`422`. Bron ko'rinmasa → `404`.
- `transition_booking` bron qatorini `FOR UPDATE` qiladi (ikki admin — edge #23), tarixga yozadi, `on_commit` email.
- Dashboard tugmalari `available_targets()` dan — server rad etadigan amal UI'da ko'rsatilmaydi.
- `expire_stale_bookings` (scheduler, 5 daqiqada): hali ham `pending` bo'lsa, lock ostida `system` sifatida `expired` sababi bilan bekor qiladi.
- Status alohida action endpointlar orqali o'zgaradi (`/confirm`, `/cancel`, `/complete`), `PATCH status` emas (ADR-007).

## 6. Vaqt zonalari (ADR-009)

- DB va service qatlami: faqat aware UTC (`TIME_ZONE = "UTC"`, `USE_TZ = True`).
- Ish vaqti qoidalari — xodimning mahalliy `time` qiymatlari (xodim zonasi yoki biznes zonasi), har sana uchun UTC'ga aylantiriladi.
- API kirishi: datetime **offset bilan majburiy** (`AwareDateTimeField`); offset'siz → `422`. Sana parametrlari (`date`, `from`, `to`) so'rovchining zonasida (`?tz=` → profil → biznes).
- API chiqishi: UTC `Z` + `start_at_local` / `start_local`.
- HTML: `DisplayTimezoneMiddleware` zonani faollashtiradi: profil → sessiya (anonim) → biznes (`/api/` va `/healthz` bundan mustasno). Brauzer zonasi farq qilsa ogohlantirish chizig'ida "Qurilma zonasiga o'tish" tugmasi (`POST /timezone/`, IANA bo'yicha tekshiriladi).
- Kalendar eksporti (`bookings/ical.py`, RFC 5545): vaqtlar UTC `Z`, UID bron ID'sidan, `SEQUENCE` status o'zgarishlari soni — kalendar bekor qilishni yangilanish sifatida qabul qiladi.

## 7. Autentifikatsiya va ruxsatlar

- Bitta `User` jadvali; API — simplejwt (access 15 daq, refresh 7 kun, rotation + blacklist, **token oilasi**: qayta ishlatilgan refresh butun login zanjirini bekor qiladi — edge #30); UI — Django session, CSRF.
- Ro'yxatdan o'tish faqat `customer`; `provider`/`admin` ni admin yaratadi.
- Ko'rinish: mijoz — o'ziniki, xodim — o'ziga bog'langan `Provider` niki, admin — hammasi (`bookings.selectors.visible_bookings`). Begona obyekt → `404`.
- Throttle: anon 60/daq, user 120/daq, login 10/daq (IP), `POST /bookings` 10/daq. Proksi orqasida `NUM_PROXIES=1`.
- Prod: HSTS, secure cookie'lar, SSL redirect (`/healthz` bundan mustasno), `check --deploy` CI'da.

## 8. Xato formati

Hamma API xatolari bitta shaklda (RFC 9457 uslubi), `apps/common/exceptions.py`:

```json
{"type": "https://navbat.uz/errors/slot-taken", "title": "Bu vaqt band", "status": 409,
 "code": "SLOT_TAKEN", "detail": "Tanlangan vaqt boshqa mijoz tomonidan band qilindi…"}
```

`errors` faqat `422 VALIDATION_ERROR` da. `DomainError`, DRF istisnolari, `Http404`, exclusion `IntegrityError` (→ 409), `OperationalError` (→ 503) va `/api/` ostidagi noma'lum URL (JSON 404) — hammasi shu shaklga tushadi. Kodlar ro'yxati va har endpoint uchun mumkin bo'lgan kodlar: `/api/docs/` (Swagger, `spectacular --validate --fail-on-warn` bilan tekshiriladi). HTML tomonda xuddi shu `DomainError.message` toast sifatida ko'rsatiladi.

## 9. Email (ADR-006)

`transaction.on_commit` → `apps/notifications/senders.py`. Rollback bo'lsa xat yo'q (edge #37); SMTP xatosi bronni qaytarmaydi va loglanadi (edge #29). Navbat (Celery) yo'q — bitta jarayon.

## 10. Nega shu texnologiyalar

| Tanlov | Sabab | Muqobil va nega emas |
|---|---|---|
| Django + DRF | ORM, migratsiya, auth, admin tayyor; serializer/permission/throttle standart | FastAPI — auth, admin, migratsiyani yig'ish kerak bo'lardi |
| PostgreSQL 16 | `EXCLUDE USING gist` — double booking DB darajasida; `tstzrange`, `timestamptz` | SQLite/MySQL exclusion constraint'ni bilmaydi; testlar ham Postgres'da |
| HTMX + Alpine + Tailwind (ADR-002) | Bitta deploy, bitta stack; slot tanlagich HTMX partial bilan; JS o'chiq bo'lsa ham mijoz formasi ishlaydi | React SPA — alohida build/deploy/CORS/token saqlash; API tayyor, keyin qo'shish mumkin |
| `on_commit` email | Kam qism, to'g'ri tartib | Celery — hozirgi hajmga ortiqcha |
| Bitta biznes (ADR-001) | Bron to'g'riligiga e'tibor | Multi-tenant — har so'rov va constraint'ga `business_id` |

## 11. Trade-off'lar

- Bitta xodimga bronlar ketma-ket yoziladi (lock) — kichik biznes uchun cheklov emas; turli xodimlar parallel.
- Slotlar har so'rovda qayta hisoblanadi (cache yo'q) — bitta xodim/kun uchun millisekundlar.
- Email so'rov ichida commit'dan keyin yuboriladi — SMTP sekin bo'lsa javob kechikadi (lock allaqachon bo'shagan).
- `static/css/app.css` repoda saqlanadi (Node'siz ishga tushirish uchun); CI uning shablonlarga mosligini tekshiradi.
- Dashboard ish vaqti muharriri Alpine'ga tayanadi (ichki foydalanuvchilar); mijoz qismi JS'siz ham ishlaydi.

## 12. O'sganda nimani qayta ko'rib chiqaman

| Signal | Yechim |
|---|---|
| Slot so'rovlari DB'ni band qiladi | Redis cache: kalit `(provider, sana)`, bron/qoida/time off yozilganda invalidatsiya (service qatlamida bitta joy) |
| Email kechikishi yoki yo'qolishi | Outbox jadvali + worker yoki Celery; `senders` o'zgarmaydi, faqat chaqiruv joyi |
| Uchrashuv oldidan eslatma kerak | Scheduler'ga ikkinchi vazifa (outbox bilan birga) |
| O'qish yuklamasi | Read replica — `selectors` allaqachon alohida, routing shu qatlamda |
| Bir nechta biznes / filial | Multi-tenant: jadvallarga `business_id`, tenant middleware, constraint'lar o'zgarmaydi (xodim bitta biznesga tegishli) |
| Mobil ilova / SPA | Tayyor API (JWT, OpenAPI); CORS whitelist qo'shiladi |
| Ko'p xodimli katta biznes | "Istalgan xodim" (bonus): engine bir nechta xodim bo'sh oynalarini birlashtiradi, yaratishda eng bo'sh xodim lock qilinadi |
