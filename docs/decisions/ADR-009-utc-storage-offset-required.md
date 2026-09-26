# ADR-009: Vaqt UTC'da saqlanadi, API'da offset majburiy

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Biznes `Asia/Tashkent` (UTC+5) da ishlaydi, lekin mijoz boshqa zonada bo'lishi mumkin (Dubay, +4), xodimning zonasi alohida sozlanishi mumkin, kelajakda DST'li mamlakat ham qo'llab-quvvatlanishi kerak. Bitta bron uchta tomonda — mijoz, xodim, server — bir xil lahza bo'lishi shart.

## Variantlar

1. **Hammasini UTC'da saqlash** (`timestamptz`, `USE_TZ=True`), mahalliy vaqt faqat kirish/chiqishda.
2. **Biznes mahalliy vaqtida saqlash** (naive datetime). Oddiy ko'rinadi, lekin boshqa zonadagi mijoz va DST'da noaniqlik beradi.
3. **Offset'siz kirishni biznes zonasi deb qabul qilish.** Qulay, lekin mijoz o'z vaqtini yuborsa, bron jimgina 1–2 soat siljiydi.

## Tanlov

- DB va service qatlami: faqat aware UTC `datetime` (`TIME_ZONE = "UTC"`, `USE_TZ = True`).
- Ish vaqti qoidalari mahalliy `time` sifatida saqlanadi va har bir aniq sana uchun alohida UTC'ga aylantiriladi (DST uchun to'g'ri).
- API kirishida datetime **offset bilan majburiy** (`2026-10-01T09:00:00+05:00` yoki `...Z`). Offset'siz qiymat → `422 VALIDATION_ERROR`. Bu `apps/api/fields.py::AwareDateTimeField` da.
- API chiqishida datetime UTC (`Z`); kerakli joyda qo'shimcha `*_local` maydoni so'rovdagi `tz` bo'yicha.

## Sabab

- Taxmin qilingan zona — eng xavfli xato turi: hech qanday xato chiqmaydi, bron noto'g'ri soatga tushadi. Rad etish esa darhol ko'rinadi.
- PostgreSQL `timestamptz` va `tstzrange` exclusion constraint UTC lahzalar ustida to'g'ri ishlaydi.
- Oraliqlarni solishtirish (time off, bronlar) — lahzalarni solishtirish, matnni emas (`test_offsets_are_compared_as_instants`).

## Oqibatlar

- Mijoz ilovasi har doim offset yuborishi kerak; bu hujjatda va xato xabarida aytilgan.
- Sana (`date=YYYY-MM-DD`) parametrlari mijoz zonasida talqin qilinadi (`tz` parametri yoki profil), engine UTC oraliqlar bilan ishlaydi.
- Testlar `freezegun` bilan UTC lahzani qotiradi.
