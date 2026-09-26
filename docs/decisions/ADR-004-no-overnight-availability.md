# ADR-004: Ish vaqti qoidasi yarim tundan o'tmaydi

- **Holat:** qabul qilingan
- **Sana:** 2026-09-26

## Kontekst

`AvailabilityRule` — haftalik takrorlanuvchi ish oynasi: `weekday`, `start_time`, `end_time`, xodimning mahalliy vaqtida. Ba'zi bizneslar (tungi klub yonidagi sartaroshxona, 24/7 klinika) 22:00–02:00 kabi smenaga ega bo'lishi mumkin. Bunday smena ikki kalendar kunga tegishli.

## Variantlar

1. **Taqiqlash:** `start_time < end_time` (DB CHECK + serializer). Tungi smena ikki qoidaga bo'linadi: juma 22:00–23:55 va shanba 00:00–02:00.
2. **Ruxsat berish:** `end_time < start_time` bo'lsa "ertasi kungacha" deb talqin qilish. Slot engine har kun uchun oldingi kunning qoidalarini ham ko'rib chiqishi, kesishish tekshiruvi kunlar chegarasidan o'tishi, UI grid'i ikki kunga cho'zilgan blokni chizishi kerak.
3. **Davomiylik bilan saqlash:** `start_time` + `duration_minutes`. Oxiri hisoblanadi, lekin kesishish va ko'rsatish yanada murakkablashadi.

## Tanlov

1-variant. DB: `CHECK (start_time < end_time)`. API: `end_time < start_time` bo'lsa `422 VALIDATION_ERROR` va aniq xabar: "Yarim tundan o'tuvchi smena qo'llab-quvvatlanmaydi, ikki kunga bo'ling".

## Sabab

- Maqsadli biznes (sartaroshxona, salon, klinika) kunduzi ishlaydi; tungi smena kam uchraydi.
- Slot engine "bitta kun = shu kunning qoidalari" bo'lib qoladi — sof va sinashga oson.
- Tungi smena kerak bo'lsa, ikki qoida bilan ifodalanadi; yo'qotiladigan narsa faqat 23:55–00:00 oralig'i (`time` tipida 24:00 yo'q).

## Oqibatlar

- 23:59 dan keyingi oxirgi daqiqalar va 00:00 chegarasidan o'tadigan bitta slot (masalan 23:30–00:30) v1'da bron qilinmaydi.
- Kerak bo'lsa keyin: `end_time` ni "kun boshidan daqiqalar" (0–1440+) ko'rinishida saqlash va engine'ni oldingi kunni ham o'qiydigan qilish — migratsiya mumkin, API shakli o'zgarmaydi.
- Edge case #16 testi: `test_edge_16_rule_crossing_midnight_rejected`.
