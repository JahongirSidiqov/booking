# ADR-003: Double booking — provider lock + exclusion constraint

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Bir xodimga bir vaqtda ikki faol bron bo'lmasligi kerak — tizimning asosiy kafolati. Xavf: ikki mijoz bir lahzada bitta slotni bosadi (edge #1), mijoz tugmani ikki marta bosadi (edge #2), yoki bron kelajakda boshqa yo'l bilan yoziladi (Django admin, shell, yangi endpoint, bug). Bir mijozning o'zi ham bir vaqtda ikki joyda bo'la olmaydi (edge #24).

## Variantlar

1. **Faqat ilova tekshiruvi** ("SELECT … bor-mi?", keyin INSERT). Poyga holatida ikkala so'rov ham "bo'sh" deb ko'radi — double booking.
2. **Faqat `select_for_update` lock.** Poyga navbatga tiziladi, lekin himoya faqat lock oladigan kod yo'lida. Admin, shell yoki lock'ni unutgan kelajakdagi kod uni aylanib o'tadi.
3. **Faqat DB exclusion constraint.** Kafolat mutlaq, lekin har poyga `IntegrityError` bilan tugaydi; uni ushlamasak — 500, ushlasak ham tekshiruv mantiqi (lead time, ish vaqti) constraint'dan oldin ishlamaydi.
4. **Serializable izolyatsiya.** Butun tranzaksiyani qayta urinish kerak bo'ladi; murakkab va sekin.
5. **Lock + constraint** (tanlangan).

## Tanlov

- `create_booking` tranzaksiya ichida **faqat shu xodimning `Provider` qatorini** `SELECT … FOR UPDATE` bilan qulflaydi. Keyin: idempotency tekshiruvi → slot engine (`slot_rejection`) → mijoz kesishuvi → `INSERT`.
- `Booking` jadvalida ikkita `ExclusionConstraint` (`btree_gist`):
  - `no_overlap_per_provider`: `provider WITH =`, `tstzrange(start_at, end_at, '[)') WITH &&`, `WHERE status IN ('pending','confirmed')`;
  - `no_overlap_per_customer`: xuddi shunday `customer` bo'yicha.
- `IntegrityError` constraint nomi bo'yicha domen xatosiga aylantiriladi: `SLOT_TAKEN` / `CUSTOMER_OVERLAP` (409).
- Idempotency tekshiruvi lock **ichida** — ikkinchi bosish birinchisining commit'ini kutadi va o'sha bronni qaytaradi (200 + `Idempotent-Replayed: true`).

## Sabab

- Lock poygani **tartibga soladi**: ikkinchi so'rov kutadi, keyin g'olibning qatorini ko'radi va odatdagi tekshiruvdan do'stona 409 oladi.
- Constraint **kafolat beradi**: lock'siz har qanday yo'l ham kesishuvchi qator yoza olmaydi.
- Lock faqat bitta xodim qatorida — boshqa xodimlarga bronlar parallel ketadi (`test_other_providers_are_not_blocked`).
- Mijoz kesishuvi turli xodimlarda (turli lock'lar) — uni faqat `no_overlap_per_customer` to'xtatadi (`test_same_customer_two_providers_at_once`).
- `[)` chegaralar: 10:00–10:30 va 10:30–11:00 kesishmaydi.

## Isbot (testlar va o'lchov)

- `tests/concurrency/test_double_booking.py::test_edge_01_ten_customers_one_slot_one_winner` — 10 thread `threading.Barrier` bilan bir lahzada `POST /bookings`: 1×201, 9×409 `SLOT_TAKEN`, DB'da 1 bron.
- `test_constraint_alone_still_yields_one_winner` — lock monkeypatch bilan o'chirilganda ham natija bir xil.
- Qo'lda o'lchov (3 marta, vaqtincha probe test bilan): lock bilan 9 yutqazuvchidan **0** tasi constraint'gacha yetdi; lock'siz har safar **1–2** tasi tekshiruvdan o'tib ketdi va faqat constraint to'xtatdi. Ya'ni ikkala qatlam ham haqiqatan ishlaydi.
- `tests/unit/test_booking_constraints.py` — ORM'ni aylanib `Booking.objects.create` bilan kesishuvchi qator → `IntegrityError`.

## Oqibatlar

- Testlar va dev ham PostgreSQL talab qiladi (SQLite exclusion constraint'ni qo'llamaydi).
- Migratsiyada `BtreeGistExtension()` birinchi operatsiya. `btree_gist` PG13+ da "trusted" — baza egasi yarata oladi.
- Bitta xodimga bron yozish ketma-ket; kichik biznes uchun (sekundiga bir necha bron) bu cheklov emas.
- Status `cancelled`/`completed` bo'lgan bronlar constraint'dan chiqadi — bekor qilingan vaqt qayta bron qilinadi.
