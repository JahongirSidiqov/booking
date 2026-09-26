# ADR-006: Email bildirishnomalari — navbatsiz, `transaction.on_commit` bilan

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

Bron yaratilganda, tasdiqlanganda va bekor qilinganda mijoz (va akkaunti bor xodim) email oladi. Talablar:

- bron saqlanmagan bo'lsa (tranzaksiya bekor bo'ldi, DB uzildi — edge #37) xat ketmasligi kerak;
- pochta serveri ishlamasa bron baribir saqlanishi kerak (edge #29);
- bitta jarayonli, kichik biznes uchun oddiy deploy.

## Variantlar

1. **View ichida to'g'ridan-to'g'ri yuborish** — tranzaksiya ichida: rollback bo'lsa ham xat ketgan bo'ladi; SMTP sekin bo'lsa provider lock'i ushlab turiladi.
2. **Celery + Redis** — ishonchli qayta urinish, lekin yana 2 ta servis (broker, worker), monitoring, deploy murakkabligi.
3. **`transaction.on_commit` + sinxron yuborish** — xat faqat commit'dan keyin; xato ushlanadi va loglanadi.
4. **Outbox jadvali + alohida jarayon** — kafolatlangan yetkazish, lekin yangi jadval va worker.

## Tanlov

3-variant.

- `bookings.services.create_booking` va `transition_booking` `transaction.on_commit(partial(sender, booking_id, ...))` qo'yadi. Rollback bo'lsa callback o'chadi — xat yo'q.
- `apps/notifications/senders.py` dagi har yuboruvchi `_never_raise` bilan o'ralgan: istisno `logger.exception("Email not sent: …")` ga yoziladi, foydalanuvchi javobi o'zgarmaydi.
- Sender bronni ID bo'yicha qaytadan o'qiydi (commit qilingan holat), matn mijozning zonasida.
- `auto_confirm` holatida bitta "tasdiqlandi" xati (ikkita emas); idempotent takrorlash xat yubormaydi; "bajarildi" holatiga xat yo'q.

## Sabab

- Kichik biznesda kuniga o'nlab xat — navbat infratuzilmasi o'zini oqlamaydi.
- `on_commit` "saqlanmagan bron haqida xat" xatosini to'liq yo'q qiladi — bu eng zararli holat.
- Xat yo'qolishi bron yo'qolishidan ancha arzon; log orqali qo'lda kuzatiladi.

## Oqibatlar

- SMTP sekin bo'lsa, javob ham shuncha kechikadi (callback so'rov ichida, commit'dan keyin ishlaydi). Lock allaqachon bo'shatilgan bo'ladi.
- Yuborilmagan xat qayta urinilmaydi. Muammo bo'lsa (ko'p `Email not sent` loglari yoki SMTP kechikishi) — 4-variant (outbox) yoki Celery'ga o'tiladi; `senders` funksiyalari o'zgarmaydi, faqat chaqiruv joyi.
- Testlar: `tests/notifications/test_emails.py` (`test_edge_29_…`, `test_edge_37_…`, `test_no_email_before_commit`).
