# Edge case'lar

TASK 8-bo'limidagi 38 ta holat: kutilgan natija, qanday hal qilingani va uni tekshiradigan test. Har bir holat uchun kamida bitta `test_edge_NN_…` nomli test bor — buni tekshirish:

```powershell
# -Quiet bilan emas: Windows PowerShell 5.1 da u har fayl uchun alohida True/False qaytaradi.
foreach ($n in 1..38) {
    $id = "{0:D2}" -f $n
    $hits = @(Get-ChildItem tests -Recurse -Filter *.py | Select-String -Pattern "def test_edge_${id}_" -List)
    if ($hits.Count -eq 0) { "yo'q: $id" }
}
```

Bitta holatni ishga tushirish: `pytest -k edge_24 -v`.

## Jadval

| # | Holat | Kutilgan natija | Qanday hal qilinadi | Test |
|---|---|---|---|---|
| 1 | Ikki mijoz bir vaqtda bitta slotni bron qiladi | Biri `201`, qolganlari `409 SLOT_TAKEN`; DB'da bitta bron | Provider qatoriga `select_for_update` + `no_overlap_per_provider` exclusion constraint (ADR-003) | `concurrency/test_double_booking.py::test_edge_01_ten_customers_one_slot_one_winner` (10 thread), `test_constraint_alone_still_yields_one_winner` (lock'siz ham) |
| 2 | Tugma ikki marta bosildi / tarmoq retry | Bitta bron; ikkinchi javob `200` + `Idempotent-Replayed: true` | `Idempotency-Key`, tekshiruv lock ichida; UI'da tugma `busy` holatida + formada kalit | `api/test_bookings.py::test_edge_02_double_click_with_same_key_creates_one_booking`, `test_parallel_retries_with_same_key_replay_one_booking`, `web/test_booking_flow.py::test_double_submit_creates_one_booking` |
| 3 | Bir xil kalit, boshqa payload | `409 IDEMPOTENCY_MISMATCH` | Payload sha256 fingerprint'i solishtiriladi | `api/test_bookings.py::test_edge_03_same_key_different_payload_is_409` |
| 4 | Slot o'tmishda yoki "hozir" | `422 IN_PAST`; UI o'tgan vaqtni ko'rsatmaydi | `now` faqat serverda; engine `start > now` | `api/test_bookings.py::test_edge_04_past_slot`, `unit/test_slot_engine.py::test_edge_04_slot_starting_right_now_is_past` |
| 5 | Lead time ichida (limit 60 daq) | `422 LEAD_TIME` | Engine `start ≥ now + min_lead_time` | `test_edge_05_inside_lead_time`, `test_edge_05_lead_time_hides_near_slots` |
| 6 | 30 kundan keyin (limit 30) | `422 TOO_FAR_AHEAD` | Engine `start ≤ now + max_advance_days` | `test_edge_06_beyond_max_advance`, `test_edge_06_beyond_max_advance_is_empty` |
| 7 | Xizmat ish vaqti oxiriga sig'maydi | Slot ko'rinmaydi; to'g'ridan-to'g'ri so'rov `422 SLOT_UNAVAILABLE` | Engine `start + duration ≤ oyna oxiri` | `test_edge_07_service_does_not_fit_before_closing`, `test_edge_07_service_must_fit_before_window_end` |
| 8 | Step'ga mos emas (10:07) | `422 STEP_MISALIGNED` | Mahalliy vaqt setkasiga tekislash (quyida) | `api/test_bookings.py::test_edge_08_step_misaligned` |
| 9 | Xodim bu xizmatni ko'rsatmaydi | `422 PROVIDER_NOT_OFFERING_SERVICE` | `scheduling.selectors.bookable_pair` | `api/test_bookings.py::test_edge_09_…`, `api/test_slots.py::test_edge_09_…` |
| 10 | Xizmat yoki xodim nofaol | `422 INACTIVE_RESOURCE`; ro'yxatlarda ko'rinmaydi, ommaga `404` | `bookable_pair`; selector'lar `is_active=True` | `test_edge_10_inactive_resource`, `api/test_services.py::test_edge_10_inactive_service_hidden_from_public`, `api/test_providers.py::test_edge_10_…` |
| 11 | Xizmat davomiyligi o'zgardi | Eski bron o'zgarmaydi; yangi slotlar yangi davomiylikda | Bronda snapshot: `duration_minutes`, `end_at` (ADR-008) | `api/test_bookings.py::test_edge_11_12_service_changes_do_not_rewrite_booking` |
| 12 | Narx o'zgardi | Eski bronda eski narx | Snapshot `price`, `service_name` | `test_edge_11_12_…`, `test_edge_12_price_change_keeps_old_price_on_booking` |
| 13 | Faol bron ustiga time off | `409 CONFLICTS_WITH_BOOKINGS` + bronlar ro'yxati; hech narsa o'zgarmaydi | `add_time_off` lock ostida faol bronlarni tekshiradi; avtomatik bekor qilish yo'q (ADR-005) | `api/test_schedule_conflicts.py::test_edge_13_…`, `web/test_dashboard.py::test_edge_13_…` |
| 14 | Ish vaqti toraytirildi, bron tashqarida qoldi | `409 CONFLICTS_WITH_BOOKINGS` + ro'yxat | `slot_engine.uncovered` — bron yangi oynalarga to'liq sig'adimi | `test_edge_14_narrowing_rule_leaving_booking_outside_is_409`, `test_edge_14_narrowing_over_booking_shows_conflict_list` |
| 15 | Bir kunda ikki qoida kesishadi (09–14, 13–18) | `422 VALIDATION_ERROR`, eski jadval saqlanadi | `replace_availability` tekshiruvi; yonma-yon (09–13, 13–18) ruxsat | `api/test_availability.py::test_edge_15_overlapping_rules_same_day_rejected` |
| 16 | Qoida yarim tundan o'tadi (22:00–02:00) | `422`, "ikki kunga bo'ling" | Serializer/forma + DB `CHECK start_time < end_time` (ADR-004) | `api/test_availability.py::test_edge_16_rule_crossing_midnight_rejected` |
| 17 | Mijoz boshqa zonada (Dubay) | Slotlar mijoz zonasida, DB'da UTC, bron to'g'ri lahzaga tushadi | `tz` param → profil → biznes zonasi; offset majburiy (ADR-009) | `api/test_slots.py::test_edge_17_…`, `api/test_bookings.py::test_edge_17_customer_offset_lands_on_same_instant` |
| 18 | DST bor mamlakat xodimi | 09:00 mahalliy vaqt DST'dan oldin ham, keyin ham 09:00 | Qoidalar har sana uchun alohida UTC'ga aylantiriladi (`zoneinfo`) | `unit/test_slot_engine.py::test_edge_18_dst_keeps_local_opening_time` |
| 19 | Mijoz muddatdan keyin bekor qilmoqchi | `422 CANCELLATION_DEADLINE_PASSED`; UI'da tugma yo'q, "biznes bilan bog'laning" | State machine guard: `now ≤ start − cancellation_deadline_hours` | `unit/test_state_machine.py::test_edge_19_…`, `api/test_booking_actions.py::test_edge_19_…`, `web/test_customer_pages.py::test_edge_19_…` |
| 20 | `cancelled`/`completed` bronni o'zgartirish | `409 INVALID_TRANSITION` | Yakuniy holatlar `TRANSITIONS` da yo'q | `test_edge_20_terminal_states_reject_everything`, `test_edge_20_cancelled_booking_is_terminal` |
| 21 | Boshlanmasdan `completed` | `409 INVALID_TRANSITION`; dashboard'da tugma ko'rinmaydi | Guard `now ≥ start_at`; `available_targets` | `test_edge_21_cannot_complete_before_start`, `test_edge_21_complete_before_start_is_409`, `web/test_dashboard.py::test_edge_21_…` |
| 22 | Vaqti o'tgan `pending` ni tasdiqlash | `409`; scheduler uni `expired` bilan bekor qiladi | Guard `now < start_at`; `expire_stale_bookings` | `api/test_booking_actions.py::test_edge_22_confirm_after_start_is_409`, `test_ops.py::test_edge_22_expire_cancels_only_past_pending` |
| 23 | Ikki admin bir vaqtda bitta bronni o'zgartiradi | Biri `200`, ikkinchisi `409`, tarixda bitta yozuv | `transition_booking` bron qatorini `select_for_update` qiladi | `concurrency/test_double_booking.py::test_edge_23_two_admins_confirm_at_once` |
| 24 | Mijozning o'zi boshqa xodimga kesishuvchi bron qiladi | `409 CUSTOMER_OVERLAP` | `no_overlap_per_customer` constraint + service tekshiruvi | `api/test_bookings.py::test_edge_24_…`, `concurrency/…::test_same_customer_two_providers_at_once` |
| 25 | Kelgusi bronlari bor xodimni deaktivatsiya qilish | Ruxsat; bronlar saqlanadi, ro'yxat qaytadi; yangi bron yo'q | `DELETE` → `200` + `upcoming_bookings`; dashboard dialogida "N ta kelgusi bron" | `api/test_bookings.py::test_edge_25_deactivating_provider_lists_upcoming_bookings`, `web/test_dashboard.py::test_service_deactivate_reports_kept_bookings` |
| 26 | Mijoz boshqa mijozning bronini ochmoqchi | `404` (403 emas) | `visible_bookings` — ko'rinmaydigan bron "yo'q" | `api/test_booking_actions.py::test_edge_26_other_customer_gets_404` |
| 27 | Slot so'rovi 90 kunlik oraliq | `400 RANGE_TOO_LARGE` | `slot_engine.validate_range` (max 31 kun) | `test_edge_27_range_too_large_is_400`, `test_edge_27_range_over_31_days_rejected` |
| 28 | Noto'g'ri `tz` (`Asia/Toshkent`) | `422` | IANA ro'yxati bilan tekshiruv | `test_edge_28_invalid_timezone_is_422`, `test_edge_28_invalid_timezone_rejected` |
| 29 | Email yuborishda xato | Bron saqlanadi, API `201`, xato loglanadi | Email `on_commit` da, har yuboruvchi `_never_raise` (ADR-006) | `notifications/test_emails.py::test_edge_29_mail_failure_keeps_booking_and_is_logged` |
| 30 | Refresh token qayta ishlatildi | `401`, shu login oilasi butunlay bekor | Token oilasi (`fam` claim), blacklist'dagi tokenni qayta ko'rsatish → oila blacklist | `api/test_auth.py::test_edge_30_refresh_reuse_revokes_whole_family` |
| 31 | Bir foydalanuvchidan ko'p bron urinishi | `429 THROTTLED` + `Retry-After` | `POST /bookings` 10/daq, login 10/daq IP, anon 60, user 120 | `api/test_bookings.py::test_edge_31_booking_attempts_are_throttled`, `api/test_auth.py::test_login_throttled_after_10_per_minute` |
| 32 | `customer_note` ichida `<script>` | Saqlanadi va API'da xom qaytadi; HTML'da eskeyplanadi | Django auto-escape; email txt `autoescape off`, html eskeyp | `api/test_bookings.py::test_edge_32_…`, `web/test_customer_pages.py::test_edge_32_note_with_script_is_escaped`, `notifications/…::test_plain_text_is_not_html_escaped` |
| 33 | Uzun o'zbek ismi (40+ belgi) | UI'da ellipsis yoki 2 qator; DB limit 120 | `truncate`/`line-clamp`, `min-w-0`; `fieldset { min-width: 0 }` | `web/test_booking_flow.py::test_edge_33_long_names_are_truncated_not_overflowing`, `e2e/test_ui_browser.py` (360px'da gorizontal scroll yo'q) |
| 34 | Xizmat 45 daq, step 15, 09:00 band | Keyingi slot 09:45 | Quyidagi tekislash qoidasi | `unit/test_slot_engine.py::test_edge_34_duration_45_step_15_next_slot_after_booking` |
| 35 | Provider `user` bilan bog'lanmagan | Faqat admin boshqaradi; bog'lanmagan xodim-foydalanuvchi hech narsa ko'rmaydi (`403`/bo'sh + tushuntirish) | `can_manage_provider`, `visible_bookings` | `api/test_availability.py::test_edge_35_…`, `api/test_booking_actions.py::test_edge_35_…`, `web/test_dashboard.py::test_edge_35_…` |
| 36 | `auto_confirm=True` | Yaratishda `confirmed`, tarixda 2 yozuv, bitta "tasdiqlandi" xati | `create_booking` → `_apply(system)` | `api/test_bookings.py::test_edge_36_…`, `notifications/…::test_edge_36_auto_confirm_sends_one_confirmed_email` |
| 37 | Tranzaksiya o'rtasida DB uzildi | Hech narsa saqlanmaydi, `503`, email yo'q | `atomic` + `on_commit`; handler `OperationalError → 503` | `api/test_api_polish.py::test_edge_37_…`, `notifications/…::test_edge_37_rolled_back_booking_sends_no_email` |
| 38 | Mijozning "1-oktabri" xodimning 30-sentabr kechqurunidir | `date` mijoz zonasida, engine ikkala xodim sanasini oladi va natijani mijoz kuniga qirqadi | `get_available_slots(tz=…)` | `unit/test_slot_engine.py::test_edge_38_customer_date_maps_to_previous_provider_evening` |

## Qo'lda sinash (curl)

Tayyorgarlik: `python manage.py seed_demo`, `python manage.py runserver`. PowerShell'da `curl.exe` ishlating.

```bash
# Token olish
curl -s -X POST localhost:8000/api/v1/auth/token -H "Content-Type: application/json" \
     -d '{"email":"mijoz@navbat.uz","password":"Navbat-Demo-2026"}'
TOKEN=...   # "access"

# Xizmat va xodim id'lari
curl -s localhost:8000/api/v1/services
curl -s "localhost:8000/api/v1/providers?service=<service_id>"

# #27 — 90 kunlik oraliq
curl -s "localhost:8000/api/v1/availability/days?service=<s>&provider=<p>&from=2026-10-01&to=2026-12-29"
# → 400 RANGE_TOO_LARGE

# #28 — noto'g'ri zona
curl -s "localhost:8000/api/v1/availability/slots?service=<s>&provider=<p>&date=2026-10-01&tz=Asia/Toshkent"
# → 422 VALIDATION_ERROR, errors.tz

# #8 — step'ga mos emas
curl -s -X POST localhost:8000/api/v1/bookings -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"service_id":"<s>","provider_id":"<p>","start_at":"2026-10-01T10:07:00+05:00"}'
# → 422 STEP_MISALIGNED

# #2 / #3 — idempotency
curl -s -i -X POST localhost:8000/api/v1/bookings -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: demo-1" \
     -H "Content-Type: application/json" -d '{"service_id":"<s>","provider_id":"<p>","start_at":"<bo'sh slot>"}'
# ikkinchi marta → 200 + Idempotent-Replayed: true; boshqa start_at bilan → 409 IDEMPOTENCY_MISMATCH

# #26 — begona bron
curl -s localhost:8000/api/v1/bookings/<boshqa mijozning bron id'si> -H "Authorization: Bearer $TOKEN"
# → 404 NOT_FOUND

# #22 — muddati o'tgan pending'larni bekor qilish
python manage.py expire_stale_bookings   # → expired: N
```

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

## Tanaffus (buffer time, bonus)

| Holat | Natija | Test |
|---|---|---|
| 09:00–09:30 bron, xizmat tanaffusi 10 daq | Xodim 09:40 gacha band; keyingi slot 09:45 (step 15) yoki 09:40 (step 5); 09:30 ga so'rov `409 SLOT_TAKEN` | `test_existing_booking_buffer_pushes_next_slot`, `test_next_booking_respects_buffer` |
| Nomzodning tanaffusi keyingi bronga kiradi (10:00 band, 30 + 15) | 09:30 ko'rsatilmaydi, 09:15 ko'rsatiladi | `test_candidate_buffer_must_not_run_into_next_booking` |
| Kunning oxirgi sloti (18:00 yopiladi, 30 + 15) | 17:30 ko'rsatiladi — tozalash yopilgandan keyin | `test_buffer_may_run_past_closing_time` |
| Mijoz tanaffus paytida boshqa xodimga yoziladi | Ruxsat — mijoz constraint'i `end_at` bo'yicha | `test_customer_is_not_blocked_by_buffer` |
| Xizmat tanaffusi keyin o'zgartirildi | Eski bronning `blocked_until` i o'zgarmaydi (snapshot) | `test_booking_snapshots_buffer_and_customer_sees_plain_times` |

## Istalgan xodim (bonus, ADR-011)

| Holat | Natija | Test |
|---|---|---|
| 09:00 ni ikki xodim band qilgan, uchinchisi 10:00 dan ishlaydi | `provider=any` slotlari 09:30 dan boshlanadi, takrorsiz | `test_slots_api_any_is_union` |
| Kunlik son | Birlashma (35), yig'indi emas | `test_days_api_any_counts_union_not_sum` |
| Bir xodimning shu kuni broni bor | Boshqa (kam band) xodim tayinlanadi, teng bo'lsa ism bo'yicha | `test_least_busy_provider_is_chosen_ties_by_name` |
| Birinchi tanlov band | Keyingi nomzodga yoziladi | `test_falls_back_when_first_choice_is_taken` |
| Hamma band yoki ishlamaydi | `409 SLOT_TAKEN` (kimdir band qilgan bo'lsa), aks holda `422 SLOT_UNAVAILABLE` | `test_provider_who_does_not_work_then_is_skipped`, `test_nobody_works_then_is_slot_unavailable` |
| O'tgan vaqt / mijozning o'zi band | Boshqa xodimlarda qayta urinilmaydi, darhol xato | `test_general_rule_fails_fast_without_trying_everyone`, `test_customer_overlap_is_not_retried_on_other_providers` |
| Qayta urinish (xuddi shu kalit), yuk o'zgargan | O'sha bron va o'sha xodim; boshqa payload → `409 IDEMPOTENCY_MISMATCH` | `test_idempotent_retry_returns_same_provider` |
| 4 mijoz bir vaqtda "istalgan", 3 xodim | 3 × 201 (3 xil xodim), 1 × 409 | `test_any_provider_parallel_bookings_spread_over_free_providers` |
| Xizmatni bitta xodim ko'rsatadi | "Istalgan xodim" kartasi ko'rsatilmaydi | `test_any_option_hidden_when_only_one_provider` |

## Ko'lamdan tashqari (ongli ravishda)

- Yarim tundan o'tuvchi smena — ADR-004.
- Jadval o'zgarganda bronlarni avtomatik bekor qilish yoki boshqa xodimga ko'chirish — ADR-005 (ko'chirish — bonus).
- Uchrashuv oldidan eslatma xati — scheduler talab qiladi; v1 da yo'q va UI'da va'da qilinmaydi.
- 23:55–00:00 oralig'i: `time` tipida 24:00 yo'q, kunning oxirgi 5 daqiqasi bron qilinmaydi (ADR-004).
