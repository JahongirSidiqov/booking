# ADR-005: Jadval o'zgarganda bronlar avtomatik bekor qilinmaydi

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Admin yoki xodim time off qo'shishi (kasallik, ta'til) yoki haftalik ish vaqtini toraytirishi mumkin. Bu vaqtga allaqachon faol (`pending`/`confirmed`) bronlar tushgan bo'lishi mumkin (edge #13, #14).

## Variantlar

1. **Avtomatik bekor qilish** — o'zgarish saqlanadi, to'qnashgan bronlar `cancelled` bo'ladi, mijozga email ketadi.
2. **Jim saqlash** — o'zgarish saqlanadi, bronlar o'z holicha qoladi (xodim yo'q paytga bron).
3. **Rad etish** — `409 CONFLICTS_WITH_BOOKINGS` va to'qnashgan bronlar ro'yxati; admin avval bronlarni hal qiladi.
4. (bonus) Bronni boshqa xodimga ko'chirish taklifi.

## Tanlov

3-variant. `add_time_off` va `replace_availability` provider qatorini qulflab, faol bronlarni tekshiradi:

- time off: `[start_at, end_at)` bilan kesishgan har qanday faol bron;
- ish vaqti: hali tugamagan faol bronlardan yangi qoidalar oynasiga **to'liq** sig'maydiganlari (`slot_engine.uncovered`, yonma-yon oynalar birlashtiriladi).

Javob: `409`, `code: CONFLICTS_WITH_BOOKINGS`, `bookings: [{id, start_at, end_at, status, service_name}]`. Hech narsa o'zgarmaydi.

## Sabab

- Mijoz bilan bog'lanmasdan bronni bekor qilish — yomon mahsulot: odam kelib yopiq eshikni ko'radi yoki email'ni o'qimaydi.
- Jim saqlash yanada yomon: tizim "band" deb ko'rsatgan vaqtga xodim yo'q.
- Ro'yxat admin'ga aniq ish beradi: kimga qo'ng'iroq qilish, qaysi bronni bekor qilish yoki ko'chirish.

## Oqibatlar

- Admin kasal xodimning kunini yopish uchun avval bronlarni bekor qiladi (UI 9-bosqichda buni bitta ekranda qiladi: ro'yxat → har birini sabab bilan bekor qilish → time off).
- O'tgan va bekor qilingan bronlar jadval o'zgarishiga to'sqinlik qilmaydi.
- Lock sababli jadval o'zgarishi va yangi bron bir-birini kutadi — orada "tekshiruvdan keyin bron tushib qolishi" mumkin emas.
- Testlar: `tests/api/test_schedule_conflicts.py` (`test_edge_13_…`, `test_edge_14_…`).
