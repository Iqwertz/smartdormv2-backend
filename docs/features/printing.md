# Printing and scanning (Drucken)

Residents print and scan on the dorm printer through SmartDorm and pay per page. The
Verwaltung collects the money. Code: `views/printing_views.py`, models `Device`,
`PrintSession`, `PrintJob`, `Scan`.

The printer hangs off a **Raspberry Pi** running CUPS, SANE and the SmartDorm agent. The Pi's
own code and setup live in the separate repo **`smartdorm-print-server`**. This doc covers the
backend side and the contract between the two.

## Agent model: the Pi polls, the backend never calls the Pi

```text
Resident ──upload PDF──► backend (PrintJob PENDING, file stored in media/print_jobs/)
Pi agent ──GET /api/printing/agent/commands/──► pending jobs + pending scan request
Pi agent ──GET /api/printing/agent/jobs/<id>/file/──► the PDF
Pi agent ──prints via local CUPS──► POST /api/printing/agent/jobs/<id>/status/ {status, pages, cups_job_id}
Pi agent ──scans──► POST /api/printing/scans/ (file + session_id)
```

- The agent authenticates with `DEVICE_AGENT_TOKEN` (`Authorization: Bearer …` or
  `X-Device-Token`). The rule is `HasDeviceToken`. Without a configured token, every agent
  request is refused.
- `PRINT_AGENT_MODE=true` (the default) means the backend never contacts CUPS itself.
  `cups_utils.py`, `CUPS_SERVER`, `CUPS_PRINTER_NAME` and `PI_SCAN_SERVICE_URL` belong to
  the older push model, where the backend talked to the Pi directly. They are only kept for
  going back.
- **Scan requests are claimed once:** `commands/` hands out `session.pending_scan` and clears it
  immediately. If the scan fails, the resident starts it again.

## Sessions and jobs

- **Only the first active `Device` is used.** There is one printer.
- A resident starts a session (`/api/tenants/printing/sessions/start/`). The device allows one
  active session at a time, and each resident may have one active session. A session older than
  `max_session_duration_minutes` is marked `EXPIRED` the next time someone checks.
  `allow_new_sessions` and `is_active` are the Verwaltung's switches.
- **Print** (`sessions/<id>/print/`, multipart PDF + `color_mode` + `copies`): the page
  count is taken from the PDF × copies up front. The agent's reported `pages` replaces it when
  the job completes.
- **Cost** is computed in `PrintJob.save()`, only for `COMPLETED` jobs:
  `pages × price_per_page_color` or `price_per_page_gray`. It is stored with the job, so later
  price changes don't touch old jobs.
- Scans are stored under `media/scans/temp/session_<id>/` and downloaded through the
  session's endpoints.

## Billing (Verwaltung)

- `/api/printing/tenant-billing-overview/`: per tenant, the total and the open debt (completed
  jobs with `settled_at` empty).
- `/api/printing/tenant/<id>/settle-debt/`: marks all open jobs as paid (`settled_at = now`).
- `/api/printing/device/<id>/…`: overview, statistics, settings (prices, max duration), toggles,
  ending a running session, and history.

## Setup

- Create or reset the device: `python scripts/setup_device_print.py` (needs at least one
  `Department`, the responsible Referat). The defaults are in the script.
- Backend env: `DEVICE_AGENT_TOKEN` (the same value on the Pi), `MEDIA_ROOT` must be writable.
- Pi: `SMARTDORM_API_BASE` (backend URL ending in `/api`), the token, and the CUPS printer name.
  See `smartdorm-print-server`.

## Open

The Pi scan endpoints `GET /api/printing/active-session/` and `POST /api/printing/scans/` are
still `Public`. See [../todo.md](../todo.md).
