# ADR-002: HTML UI — Django templates + HTMX, React SPA emas

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Talab — backend API (to'liq DRF, hujjatlangan, testlangan) va foydalanuvchi uchun ishlaydigan UI: mijozning bron oqimi va xodim/admin dashboard'i. Loyihani bir kishi quradi, deploy oddiy bo'lishi kerak.

## Variantlar

1. **React (yoki Vue) SPA** + DRF API. Alohida frontend loyihasi, build, deploy, CORS, JWT'ni brauzerda saqlash.
2. **Django templates + HTMX + Alpine.js + Tailwind** — server render, interaktiv joylar (slot picker, filtrlar, modal) HTMX partial va Alpine bilan.
3. **Faqat Django admin** — tez, lekin mijoz uchun yaroqsiz.

## Tanlov

2-variant. API ham, HTML UI ham bir xil `services/` va `selectors/` qatlamini chaqiradi; view'lar yupqa.

## Sabab

- Bitta stack, bitta deploy, bitta auth jadvali (UI — session, API — JWT).
- Biznes mantiq bir joyda: API va UI bir xil service funksiyasini chaqirgani uchun qoidalar ikki marta yozilmaydi va bir xil testlanadi.
- Interaktivlik talabi o'rtacha: sana/slot tanlash, filtrlar, modal. HTMX partial'lar buni SPA murakkabligisiz beradi.
- SPA uchun alohida state boshqaruvi, routing, token saqlash va CORS kerak bo'lardi — bir kishilik loyihada bu vaqtni bron to'g'riligidan oladi.

## Oqibatlar

- API mustaqil va to'liq (OpenAPI/Swagger); kelajakda SPA yoki mobil ilova shu API ustiga qurilishi mumkin.
- UI HTMX partial'lari uchun alohida server view'lar kerak; ular ham service qatlamidan foydalanadi.
- Juda boy client-side interaktivlik (drag-and-drop kalendar) kerak bo'lsa, o'sha qism alohida JS komponent sifatida qo'shiladi yoki SPA'ga o'tish qayta ko'rib chiqiladi.
