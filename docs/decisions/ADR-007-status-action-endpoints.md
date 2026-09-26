# ADR-007: Status o'zgarishi — alohida action endpointlar

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Bron holati `pending → confirmed → completed`, istalgan faol holatdan `cancelled` (TASK 5.3). Har o'tishning o'z qoidasi bor: kim bajara oladi, qachon (boshlanishdan oldin/keyin, bekor qilish muddati), qanday qo'shimcha ma'lumot kerak (xodim bekor qilsa — sabab).

## Variantlar

1. **`PATCH /bookings/{id}` `{"status": "confirmed"}`** — umumiy yangilash. Bitta endpoint, lekin har `status` qiymati uchun turli ruxsat va body kerak; OpenAPI'da "status ixtiyoriy string" bo'lib ko'rinadi; `status` ni boshqa maydonlar bilan birga yangilash imkoniyati qoidalarni aylanib o'tish yo'lini ochadi.
2. **Alohida action'lar:** `POST /bookings/{id}/confirm`, `/cancel` (`{reason}`), `/complete`.
3. **Umumiy `POST /bookings/{id}/transitions` `{"to": "..."}`** — bitta endpoint, lekin 1-variantning hujjatlash muammosi qoladi.

## Tanlov

2-variant. Har action `services.transition_booking(booking_id, to_status, actor, reason)` ni chaqiradi; qoidalar `apps/bookings/state_machine.py` dagi `TRANSITIONS` jadvalida (`(from, to) → (rollar, guard)`).

## Sabab

- Har endpointning ruxsati, body'si va xatolari OpenAPI'da aniq ko'rinadi (masalan faqat `/cancel` da `reason`).
- UI tugmalari ("Tasdiqlash", "Bekor qilish", "Bajarildi") to'g'ridan-to'g'ri endpointlarga mos.
- `status` hech qachon oddiy maydon sifatida yozilmaydi — service qatlamidan tashqarida o'zgartirish yo'li yo'q.

## Qoidalarning bajarilishi

- Xato tartibi: mavjud bo'lmagan o'tish (shu jumladan yakuniy holatdan) → `409 INVALID_TRANSITION`; o'tish mavjud, lekin rol noto'g'ri → `403 FORBIDDEN`; keyin guard'lar (`409 INVALID_TRANSITION`, `422 CANCELLATION_DEADLINE_PASSED`, `422 VALIDATION_ERROR` sabab uchun).
- Bron ko'rinmasa (boshqa mijozniki, boshqa xodimniki) → `404` — mavjudligi oshkor qilinmaydi.
- `transition_booking` bron qatorini `select_for_update` bilan qulflaydi: ikki admin bir vaqtda bossa, ikkinchisi yangi holatni ko'radi va `409` oladi (edge #23, `test_edge_23_two_admins_confirm_at_once`).
- Bir xil holatga qayta o'tish (masalan `confirmed` ni yana confirm) — no-op emas, `409`: jadvaldagi "terminal / mavjud bo'lmagan o'tish" qoidasi bilan bir xil va tushunarli.
- Uch qatlamli himoya: (1) `tests/test_architecture.py` — `apps/` da `bookings/services.py` dan tashqarida `.status =` yoki `.update(status=...)` yo'qligini grep bilan tekshiradi; (2) `Booking.save()` service belgisi bo'lmasa status o'zgarishini rad etadi; (3) Django admin'da bron faqat o'qish uchun.

## Oqibatlar

- Yangi holat qo'shish = `TRANSITIONS` ga qator + action endpoint + test matritsasiga qator.
- `tests/unit/test_state_machine.py` 4×4×4 matritsani (status × maqsad × rol) spetsifikatsiya jadvaliga solishtiradi.
