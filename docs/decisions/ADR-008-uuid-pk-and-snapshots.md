# ADR-008: UUID birlamchi kalitlar va bronda snapshot maydonlar

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Bron URL'larda ko'rinadi (`/bookings/<id>/`). Xizmat narxi, nomi va davomiyligi vaqt o'tishi bilan o'zgaradi, lekin o'tgan bron "o'sha kungi" shartlarini saqlashi kerak (edge #11, #12). Xizmat va xodimlar tarixiy bronlarga bog'langan.

## Variantlar

**Kalitlar:** (a) auto-increment `bigint`; (b) UUIDv4; (c) auto-increment + alohida ommaviy `public_id`.

**Tarix:** (a) bron faqat `service_id` ga ishora qiladi, narx/davomiylik xizmatdan o'qiladi; (b) bronga yaratish paytidagi qiymatlar nusxalanadi (snapshot); (c) xizmatni versiyalash (`ServiceVersion` jadvali).

## Tanlov

- Barcha biznes jadvallari `BaseModel`dan: `id UUID` (v4), `created_at`, `updated_at`. Istisno: `BusinessSettings` (`pk=1` singleton) va `BookingStatusHistory` (`bigint` — ichki audit, URL'da ko'rinmaydi, tartib uchun qulay).
- `Booking` da snapshot: `service_name`, `duration_minutes`, `price`. `end_at` ham yaratishda hisoblanib saqlanadi.
- `Booking` → `customer`, `provider`, `service` FK'lari `on_delete=PROTECT`; xizmat va xodim hech qachon o'chirilmaydi, faqat `is_active=False`.

## Sabab

- UUID ketma-ket ID'lar orqali bronlar sonini bilish va boshqa bronlarni sanab chiqishni qiyinlashtiradi; begona bron baribir `404` qaytaradi.
- Snapshot eng oddiy to'g'ri yechim: narx o'zgarsa eski chek o'zgarmaydi; davomiylik o'zgarsa eski bronning `end_at` i va exclusion constraint'dagi oralig'i o'zgarmaydi. Versiyalash jadvali bu loyiha uchun ortiqcha.
- `PROTECT` tarixiy bronlarni yetim qoldirmaydi; o'chirish o'rniga deaktivatsiya (`DELETE` endpoint'lari ham shunday ishlaydi).

## Oqibatlar

- UUID indekslari `bigint` dan kattaroq; bu hajmda ahamiyatsiz.
- Snapshot maydonlari xizmat nomi keyin tuzatilsa ham eski bronda eski nomni ko'rsatadi — bu ataylab.
- Testlar: `test_edge_11_12_service_changes_do_not_rewrite_booking`, `test_service_and_provider_are_protected`.
