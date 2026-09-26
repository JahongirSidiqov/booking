# Edge case'lar

## Slot boshlanishi qanday tanlanadi

Slot engine (`apps/scheduling/slot_engine.py`) bo'sh oynalardan slot yasaydi:

1. Xodimning ish oynalari (mahalliy vaqt) har bir aniq sana uchun UTC'ga aylantiriladi.
2. Oynalardan time off va band bronlar ayiriladi. Barcha oraliqlar yarim ochiq `[start, end)`.
3. Qolgan har bir oynada birinchi boshlanish — oyna boshidan keyingi **mahalliy vaqt setkasidagi** birinchi nuqta: mahalliy yarim tundan `slot_step` daqiqaga karrali (09:00, 09:15, 09:30…).
4. `start + davomiylik ≤ oyna oxiri` bo'lsa slot qo'shiladi, keyin `start += step`.
5. Filtrlar: `start > now`, `start ≥ now + min_lead_time`, `start ≤ now + max_advance_days`, `start` mijozning so'ralgan kunida.

**Davomiylik step'ga karrali bo'lmasa** (step 15):

| Xizmat | Band | Keyingi mumkin bo'lgan boshlanish | Sabab |
|---|---|---|---|
| 45 daq | 09:00–09:45 | 09:45 | Oyna 09:45 da ochiladi, 09:45 setkada |
| 40 daq | 09:00–09:40 | 09:45 | Oyna 09:40 da ochiladi, setkadagi birinchi nuqta 09:45 |
| 30 daq | 10:00–10:30 | 09:30 ham, 10:30 ham mumkin | `[)`: 09:30–10:00 va 10:30–11:00 bron bilan kesishmaydi |

Setka UTC'ga emas, mahalliy yarim tunga bog'langan: UTC+5:45 (Kathmandu) zonasida ham mijoz 09:00, 09:30 ni ko'radi, 09:15/09:45 ni emas.

Testlar: `test_edge_34_duration_45_step_15_next_slot_after_booking`, `test_duration_40_rounds_up_to_next_step_after_booking`, `test_busy_range_half_open_boundaries`, `test_alignment_uses_local_grid_in_quarter_hour_offset_zone` (`tests/unit/test_slot_engine.py`).
