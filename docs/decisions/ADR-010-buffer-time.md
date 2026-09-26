# ADR-010: Xizmatdan keyingi tanaffus (buffer time)

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Ba'zi xizmatlardan keyin xodimga vaqt kerak: joyni tozalash, asboblarni tayyorlash (masalan "Yuz parvarishi" dan keyin 15 daqiqa). Bu vaqtga keyingi mijoz yozilmasligi kerak, lekin mijozning o'z uchrashuvi uzaymasligi kerak (u 09:00–09:30 ga yozilgan, 09:40 gacha emas).

## Variantlar

1. **Davomiylikni oshirish** (30 → 40 daq): oddiy, lekin mijoz noto'g'ri vaqtni ko'radi, narx/uchrashuv mazmuni buziladi.
2. **Biznes bo'yicha bitta buffer** sozlamalarda: hamma xizmatga bir xil — soch olishga keraksiz, yuz parvarishiga yetmaydi.
3. **Xizmat bo'yicha "keyingi" buffer** (`Service.buffer_after_minutes`), bronda snapshot va `blocked_until` (tanlangan).
4. Oldingi + keyingi buffer (Calendly uslubi) — hozircha ehtiyoj yo'q; "keyingi" bilan ifodalanadi.

## Tanlov

- `Service.buffer_after_minutes` (0–120, 5 ga karrali, DB CHECK).
- `Booking.buffer_minutes` — snapshot; `Booking.blocked_until = end_at + buffer`, `CHECK blocked_until ≥ end_at`.
- **Xodim** exclusion constraint'i `[start_at, blocked_until)` ni tekshiradi; **mijoz** constraint'i va mijozga ko'rinadigan vaqt `[start_at, end_at)` bo'lib qoladi — tanaffus paytida mijoz boshqa xodimga yozila oladi.
- Slot engine: band oraliqlar `blocked_until` gacha (mavjud bronning tanaffusi) va nomzodning o'z tanaffusi keyingi bronga kirmasligi uchun band oraliqlar boshlanishi `buffer` qadar oldinga suriladi. Ish vaqti oxiri surilmaydi — kunning oxirgi mijozidan keyin tozalash yopilgandan keyin ham bo'lishi mumkin.
- Time off va jadval toraytirish tekshiruvlari `end_at` bo'yicha (tanaffus ish vaqtidan tashqariga chiqishi mumkin).

## Sabab

- Tanaffus xizmatning xususiyati (turli xizmatda turlicha) va o'tmishdagi bronlar uchun o'zgarmasligi kerak — narx/davomiylik bilan bir xil snapshot mantig'i (ADR-008).
- DB kafolati saqlanadi: `blocked_until` saqlangan ustun bo'lgani uchun exclusion constraint oddiy `tstzrange` ustida qoladi, ifodali indeks kerak emas.

## Oqibatlar

- Migratsiya qo'lda yozilgan: eski bronlar uchun `blocked_until = end_at`, xodim constraint'i yangi chegarada qayta yaratildi.
- Mijoz API'si va sahifalari o'zgarmadi; `buffer_after_minutes` faqat admin serializer'ida va dashboard formasida. Kun ko'rinishida tanaffus shtrixli qism bilan ko'rsatiladi.
- Testlar: `tests/api/test_buffer_time.py` (engine, DB, API, dashboard).
