# Suhbat uchun qisqa javoblar

## Double booking'dan qanday himoyalangansiz?

Uch qatlam, har biri boshqasi ushlamaydigan narsani ushlaydi:

1. **UI** — "Bronni tasdiqlash" bosilgach tugma o'chadi, formada `idempotency_key` bor: ikki marta bosish bitta bron (ikkinchisi 200 replay).
2. **Lock** — `create_booking` tranzaksiyada faqat shu xodimning qatorini `SELECT … FOR UPDATE` qiladi. Poygadagi ikkinchi so'rov kutadi, keyin g'olibning bronini ko'rib do'stona `409 SLOT_TAKEN` oladi (500 emas). Boshqa xodimlarga bronlar parallel ketadi.
3. **Constraint** — `EXCLUDE USING gist (provider WITH =, tstzrange(start_at, end_at, '[)') WITH &&) WHERE status IN (pending, confirmed)`. Lock'ni chetlab o'tgan har qanday yo'lni to'xtatadi: admin, shell, kelajakdagi bug, bitta mijozning bir vaqtda ikki xodimga yozilishi (turli lock'lar — faqat `no_overlap_per_customer` to'xtatadi).

Nega bittasi yetmaydi: faqat lock — lock olmaydigan kod himoyasiz; faqat constraint — har poyga `IntegrityError`, validatsiya tartibi buziladi. Isbot: 10 thread bitta slotga → 1×201, 9×409; lock o'chirilganda ham 1 g'olib; o'lchovda lock bilan 0 ta, lock'siz 1–2 ta so'rov constraint'gacha yetdi.

## Nega service qatlami?

Bitta yozish nuqtasi, ikki interfeys. API va HTML UI bir xil `create_booking` / `transition_booking` ni chaqiradi — qoida bir marta yoziladi va bir marta testlanadi. `Booking.status` ni faqat `bookings/services.py` o'zgartiradi: grep testi, `save()` himoyasi, admin'da faqat o'qish. View'lar yupqa: kirish → service → chiqish.

## Nega `[)` oraliq?

10:00–10:30 va 10:30–11:00 kesishmasligi kerak. `[)` (yarim ochiq) bilan chegaradagi daqiqa bitta bronga tegishli — ketma-ket bronlar va "09:30 dagi slot 10:00 dagi bron oldidan" to'g'ri ishlaydi. Engine ham, DB ham bir xil semantikada.

## Nega snapshot?

Bronda `service_name`, `duration_minutes`, `price`, `end_at` saqlanadi. Xizmat narxi yoki davomiyligi o'zgarsa eski bron o'zgarmaydi — chek, tarix va constraint oralig'i o'sha kungidek. Versiyalash jadvali bu hajmda ortiqcha.

## Nega begona bronga 404, 403 emas?

403 "bunday bron bor, lekin sizniki emas" degani — ID'lar orqali boshqa mijozlarning bronlari mavjudligini tekshirish mumkin bo'lardi. 404 hech narsa oshkor qilmaydi. UUID kalitlar bilan birga sanab chiqish amalda imkonsiz.

## Vaqt zonalari qanday ishlaydi?

- DB va service: faqat UTC.
- Ish vaqti qoidalari xodimning mahalliy vaqtida saqlanadi va **har bir aniq sana uchun** UTC'ga aylantiriladi — DST bo'lsa ham 09:00 mahalliy vaqt 09:00 bo'lib qoladi.
- API kirishida offset majburiy: `2026-10-01T09:00:00` (offset'siz) taxmin qilinmaydi, `422`. Taxmin qilingan zona — jim xato: bron bir-ikki soat siljiydi.
- Mijozning "1-oktabri" xodimning 30-sentabr kechqurunida bo'lishi mumkin — engine ikkala sanani oladi va mijoz kuniga qirqadi.
- Step setkasi UTC'ga emas, mahalliy yarim tunga bog'langan: UTC+5:45 da ham 09:00, 09:30.

## State machine qanday qurilgan?

`TRANSITIONS: dict[(from, to) → (rollar, guard, sabab kimga majburiy)]` — sof ma'lumot. `transition_booking` bron qatorini lock qiladi (ikki admin bir vaqtda → biri 200, biri 409), jadval bo'yicha tekshiradi, tarixga yozadi, `on_commit` email. Dashboard tugmalari `available_targets()` dan — server rad etadigan amal ko'rsatilmaydi. Testda 4×4×4 matritsa (holat × maqsad × rol) spetsifikatsiya jadvaliga solishtiriladi.

## Email xato bersa?

Xat `transaction.on_commit` da yuboriladi: rollback bo'lsa xat yo'q, SMTP xatosi bronni qaytarmaydi — yuboruvchi istisnoni loglaydi, API 201 qaytaradi. Queue (Celery) yo'q — kichik hajmda ortiqcha; kerak bo'lsa outbox jadvali.

## Tizim o'sganda nima o'zgaradi?

- **Slot cache** — Redis, kalit `(xodim, sana)`, bron/qoida/time off yozilganda invalidatsiya; yozish nuqtasi bitta bo'lgani uchun invalidatsiya ham bitta joyda.
- **Email navbati** — outbox + worker yoki Celery; `senders` o'zgarmaydi.
- **Read replica** — `selectors` allaqachon alohida, routing shu yerda.
- **Multi-tenant** — jadvallarga `business_id`, tenant middleware; exclusion constraint'lar o'zgarmaydi (xodim bitta biznesga tegishli).

## Eng qiyin joy nima bo'ldi?

Vaqt: xodim zonasi, mijoz zonasi, DST, mahalliy step setkasi va "mijoz kuni ≠ xodim kuni". Yechim — engine'ni sof funksiya qilish va har qoidani qo'lda hisoblangan qiymatlar bilan unit test qilish; testlar haqiqatan xatoni ushlashini engine'ga ataylab xato kiritib tekshirdim (mutatsion tekshiruv).

## Nimani boshqacha qilgan bo'lardim?

- Brauzer testlarini (Playwright) boshidan qo'shish — eng qiziq UI xatolari (o'zbek lokalizatsiyasida CSS'dagi vergulli foizlar, 360px'da `fieldset` kengayishi, dialog'ning o'zi yopilishi) faqat haqiqiy brauzer va skrinshotlarda ko'rindi, Django testlari ushlamadi.
- Production `collectstatic` ni birinchi kundan CI'da ishga tushirish — Tailwind manbasi `static/` ichida bo'lgani prod konteynerni ishga tushirmas edi.
