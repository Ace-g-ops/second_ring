# Stale callback maintenance (operators only)

Run from the backend repository with its normal Python dependencies installed.
This is **not an HTTP endpoint**. Give shell access/database credentials only to
authorized operators. Never put these credentials into the dashboard.

Supply `DATABASE_URL`, `BIMPEAI_API_KEY`, and `BIMPE_AGENT_ID` in the process
environment using your usual secret manager. The command never displays their
values or external exception messages. Use the same agent/database as the
callback; a wrong agent's empty history cannot prove an orphan.

## Review first

```sh
python scripts/repair_callback.py \
  --missed-call-id MISSED_CALL_ID \
  --attempt-start 2026-10-01T10:00:00Z \
  --attempt-end 2026-10-01T12:00:00Z
```

No writes occur without `--apply`. The ID and timezone-aware attempt bounds are
required. Use server/operator records to select the **entire** attempted-callback
window, not a narrow interval chosen to exclude alternative matches. The legacy
schema has no attempt-start field; missed/created timestamps are not proof of
when a callback began. Do not guess the bounds. The window must end at least
24 hours ago by default; `--stale-hours N` may change that, with a one-hour floor.
Wait for provider history to settle before attempting a repair.

The report shows related log/bookings IDs, statuses and timestamps, matching
provider IDs, and the proposed action or blocking reasons. It omits phone
numbers, names, transcripts and error text. Inspect richer sensitive evidence
only through existing authorized operational tools. The command reviews the
entire agent history including test calls, all statuses and all pages. Absent,
inconsistent, changing or incomplete pagination fails closed. A provider outage
is never treated as empty history.

Recovery requires exactly one outbound call with an exact international
recipient match in the reviewed window, no conflicting log IDs, no competing
unresolved attempts, and no association of that provider ID to another missed
call (including call logs). Ambiguous/unverifiable cases require investigation,
not a forced repair.

## Apply one repair

After reviewing, repeat the same command with `--apply` to attach an unambiguous
provider ID. This leaves status in progress: the existing result reconciliation
can then determine the real outcome independently of booking conversion.

Only when complete history has **no** matching call and no related logs/bookings
contradict that conclusion may an operator explicitly select
`--apply --mark-orphan-failed`. This changes only the target status to `failed`.
It does **not** redial it. A later retry through the existing application remains
a separate operator decision; do not repeatedly trigger a recovered callback.

Every apply performs a fresh history review. It checks for database changes
during history retrieval and rechecks the evidence again inside the write
transaction, then requires exactly one update matching the ID, expected
`callback_in_progress` status, and NULL provider ID. Any mismatch rolls back.
On PostgreSQL the review also compares the target's row version, so leaving
and re-entering the same status with a missing ID is detected as a new attempt.
PostgreSQL briefly locks the three evidence tables during the database-only
recheck/update, preventing concurrent writers from stealing an ID or adding
contradictory evidence. Schedule maintenance at low traffic: writes may wait
briefly. No provider requests occur while these locks are held.

Never use this command for ordinary pending callbacks. It cannot delete
records, update bookings/logs, place calls or retry calls. Exit code 0 means a
successful review/apply, 2 means refused/failed review (no repair committed).
An orphan dry-run is only a proposal; it is never permission to apply without
the explicit orphan flag.

## Tests (no live service or credentials)

```sh
python -m unittest discover -s tests -v
```

Tests use isolated SQLite tables and stub provider pages; the PostgreSQL JSONB
column is compiled as JSON only in tests. They never import the configured
database or initialize a live SDK. When `initdb` and `pg_ctl` are installed,
the suite also starts a disposable PostgreSQL cluster on a private Unix socket
(no TCP listener) to check real locks, guarded recovery and stale row versions.
These tests never read `DATABASE_URL`; without the binaries they are skipped.
SQLite verifies transaction rollback and guarded row counts. Do not run root-level ad-hoc `test_db.py`,
`check_db.py`, `test.py` or `retry.py` against production as part of verification.
