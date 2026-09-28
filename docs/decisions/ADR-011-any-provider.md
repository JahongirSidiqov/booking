# ADR-011: "Istalgan xodim" — slotlar birlashmasi va avtomatik tayinlash

- **Holat:** qabul qilingan
- **Sana:** 2026-09-28

## Kontekst

Ko'p mijozga xodim muhim emas — unga eng yaqin bo'sh vaqt kerak. Xodimni majburiy tanlash vaqtni yo'qotadi: mijoz bitta xodimda 11:00 ni ko'radi, boshqasida 09:30 bo'sh ekanini bilmaydi. Tizim (1) hamma xodim bo'yicha bo'sh vaqtlarni ko'rsatishi va (2) tasdiqlashda bitta xodimni adolatli tanlashi kerak — double booking kafolatlarini (ADR-003) buzmasdan.

## Variantlar

**Tanlash qoidasi:**
1. Tasodifiy xodim — adolatli o'rtacha, lekin testlab bo'lmaydi va tushuntirish qiyin.
2. Round-robin (oxirgi tayinlangan xodimdan keyingisi) — holat saqlash kerak (yangi jadval yoki ustun), parallel so'rovlarda o'zi poyga manbai.
3. **Shu kunda eng kam faol broni bor xodim**, teng bo'lsa ism, keyin id bo'yicha (tanlangan) — holatsiz, deterministik, kun bo'yi yukni tekislaydi.

**Qulflash:**
1. Hamma nomzod xodimlarni bir tranzaksiyada `FOR UPDATE` bilan qulflash — tartib buzilsa deadlock xavfi, bitta "istalgan" so'rov butun jamoani to'xtatadi.
2. **Har nomzod uchun oddiy `create_booking` (o'z tranzaksiyasi, bitta xodim lock'i)**, rad etilsa keyingisi (tanlangan).

## Tanlov

- **Ko'rsatish:** `provider=any` — xizmatni ko'rsatadigan faol xodimlar slotlari birlashmasi (`slot_engine.union_slots`, boshlanish vaqti bo'yicha takrorsiz). Kunlik son — birlashma soni, yig'indi emas (09:00 ni uch xodim bersa ham bitta slot).
- **Yaratish:** `services.create_booking_any` nomzodlarni yuk bo'yicha tartiblab, har biriga `create_booking` ni chaqiradi. Xodimga xos rad etishlar (`SLOT_TAKEN`, `SLOT_UNAVAILABLE`, `STEP_MISALIGNED`) — keyingi nomzod; umumiy qoidalar (`IN_PAST`, `LEAD_TIME`, `TOO_FAR_AHEAD`, `CUSTOMER_OVERLAP`, faol emas) — darhol qaytariladi, boshqalarda ham takrorlanishi aniq. Hech kim olmasa — eng foydali sabab: `SLOT_TAKEN` > `SLOT_UNAVAILABLE` > `STEP_MISALIGNED`.
- **Idempotency:** payload izi `provider_id="any"` bilan hisoblanadi, tayinlangan xodim bilan emas. Qayta urinish (yuk o'zgargan bo'lsa ham) o'sha bronni qaytaradi; boshqa `note` bilan — `409 IDEMPOTENCY_MISMATCH`.
- **API:** `POST /api/v1/bookings` da `provider_id` ixtiyoriy (`null` yoki yo'q → istalgan); `GET /availability/slots|days?provider=any`, javobda `provider: null`.
- **UI:** xodim tanlash qadamida birinchi karta "Istalgan xodim" (faqat xodim 1 tadan ko'p bo'lsa); tasdiq sahifasida "tasdiqlashda tizim tanlaydi"; natija sahifasida tayinlangan xodim ismi.

## Sabab

- Hech qachon ikki xodim lock'i bir vaqtda ushlanmaydi — deadlock mumkin emas, har urinish ADR-003 dagi lock + `EXCLUDE` himoyasida.
- Poyga holatida (ikki mijoz bir vaqtda "istalgan" bilan bitta xodimni tanlasa) yutqazgan `SLOT_TAKEN` oladi va keyingi nomzodga o'tadi — natijada bronlar bo'sh xodimlarga tarqaladi. Parallel test buni isbotlaydi (3 xodim, 4 mijoz → 3 × 201, 1 × 409, 3 xil xodim).
- Yuk hisoblash holatsiz va bitta `GROUP BY` so'rovi — round-robin holatini saqlash va uni qulflash kerak emas.

## Oqibatlar

- Tanlash "eng yaxshi" emas, "yetarli adolatli": xodim malakasi yoki mijoz tarixi hisobga olinmaydi. Kerak bo'lsa tartiblash kaliti bitta joyda (`create_booking_any`) o'zgaradi.
- Yomon holatda N ta xodim uchun N ta qisqa tranzaksiya — kichik jamoada (3–10 xodim) sezilmaydi.
- Yuk tanlash paytida o'qiladi, lock'siz: parallel so'rovlar bir xil xodimni tanlashi mumkin, lekin to'g'rilikni emas, faqat taqsimotni ta'sir qiladi — fallback baribir bo'sh xodimga o'tkazadi.
- Testlar: `tests/api/test_any_provider.py` (17), `tests/concurrency/test_double_booking.py::test_any_provider_parallel_bookings_spread_over_free_providers`.
