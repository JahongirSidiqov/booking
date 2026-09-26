# ADR-001: Bitta biznes (single-tenant) ko'lami

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Navbat bir kichik xizmat biznesi (demo: "Navbat Barbershop", 3 xodim, 5 xizmat) uchun bron tizimi. Vaqt cheklangan, asosiy qiymat — to'g'ri ishlaydigan bron oqimi: bo'sh slotlar, double booking'dan himoya, status boshqaruvi, timezone.

## Variantlar

1. **Single-tenant** — bir o'rnatish = bir biznes. `BusinessSettings` singleton (`pk=1`).
2. **Multi-tenant** — har jadvalda `business_id`, subdomen/URL bo'yicha tenant aniqlash, tenant bo'yicha izolyatsiya va ruxsatlar.
3. Qo'shimcha imkoniyatlar: onlayn to'lov, SMS, mobil ilova, takrorlanuvchi bronlar.

## Tanlov

Single-tenant. Quyidagilar v1'da **ataylab qilinmaydi**: multi-tenant, onlayn to'lov, SMS, mobil ilova, recurring bookings.

## Sabab

- Multi-tenant har so'rov, har constraint va har testga `business_id` qo'shadi; xatoda bir biznes ma'lumoti boshqasiga oqib chiqishi xavfi paydo bo'ladi. Bu murakkablik v1 maqsadiga (bron to'g'riligi) hissa qo'shmaydi.
- To'lov va SMS — tashqi integratsiyalar; ular yo'qligi bron mantiqini sinashga ta'sir qilmaydi. Email bildirishnomasi yetarli.
- Recurring bookings slot engine va konflikt tekshiruvini sezilarli murakkablashtiradi.

## Oqibatlar

- Sozlamalar (timezone, step, lead time, bekor qilish siyosati) bitta `BusinessSettings` qatorida.
- Keyin multi-tenant kerak bo'lsa: barcha biznes jadvallariga `business` FK, exclusion constraint'larga `business` qo'shilmaydi (xodim allaqachon bitta biznesga tegishli), so'rovlar tenant bo'yicha filtrlanadi. Bu migratsiya mumkin, lekin hozir to'lanmaydi.
- Bir nechta filial kerak bo'lsa — hozircha alohida o'rnatish.
