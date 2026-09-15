# 04 — `TIME_ZONE = 'UTC'` puts the wrong date on the SEPA mandate

**Severity:** High — corrupts the evidence chain the whole feature is built around.
**Area:** Evidence / mandate register
**Status:** open

---

## Instructions for the agent

Read this entire file first. This one has blast radius beyond the membership feature: the
settings change affects every timestamp rendered anywhere in SmartDorm.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available.

---

## What is wrong

`smartdorm/settings.py` (~line 73) sets `TIME_ZONE = 'UTC'` with `USE_TZ = True`. Storage in
UTC is correct and should stay. The bug is that two places render or truncate an aware
datetime without converting to local time first:

1. **`smartdorm/utils/membership_pdf.py`** (~line 158), in the "Dokumentation der Abgabe"
   block:
   ```python
   application.submitted_at.strftime('%d.%m.%Y um %H:%M:%S Uhr')
   ```
   This prints UTC and labels it "Uhr" on a German legal document. It is off by one hour in
   winter and two in summer, always.

2. **`smartdorm/views/membership_views.py`** (~line 433), in `decide_application_view`:
   ```python
   mandate_signed_on=application.submitted_at.date() if is_sepa else None,
   ```
   `.date()` on an aware UTC datetime yields the **UTC** calendar date.

The consequence: a member who submits at 00:30 CEST on 2 July gets a mandate dated 1 July,
and an archived PDF that says "01.07.2026 um 22:30 Uhr". Any submission after 22:00 (summer)
or 23:00 (winter) local time lands on the wrong day.

That date is not cosmetic. `mandate_signed_on` is written into every `pain.008` as the
mandate signature date (`sepa_utils.build_direct_debit_xml`, the `mandate_date` key). When a
member disputes a collection, the bank matches the mandate ID *and* that date against the
mandate document the Verein produces. Here the two disagree by a day — and they disagree in
the one document whose entire purpose, per the module docstring in `membership_pdf.py`, is to
be the Verein's evidence.

## Why it is wrong / how it got here

`TIME_ZONE = 'UTC'` is a sensible default and is fine for storage; Django's own docs
recommend it. The gap is that Django only converts to local time automatically in *template*
rendering. Everywhere you format a datetime in Python — ReportLab, `strftime`, `.date()` —
you get UTC unless you call `timezone.localtime()` yourself. This feature is the first part
of SmartDorm where the difference has legal weight, so it is the first place it hurts.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/settings.py` | `TIME_ZONE`, `USE_TZ` |
| `smartdorm/utils/membership_pdf.py` | `render_declaration_pdf`, the submission-record table |
| `smartdorm/views/membership_views.py` | `decide_application_view` (`mandate_signed_on`), `update_mandate_view`, `_age_on` |
| `smartdorm/utils/sepa_utils.py` | `build_direct_debit_xml` — consumes `mandate_signed_on` |
| everywhere else | `grep -rn "timezone.now()" smartdorm/ --include="*.py"` — other features may quietly rely on UTC |

## Questions to ask first

1. **Change `TIME_ZONE` to `Europe/Berlin`, or leave it UTC and convert at every render
   site?** Changing the setting fixes this and every future instance at once, but it changes
   how *all* existing SmartDorm timestamps render (printing sessions, attendance, departures)
   and how `timezone.now().date()` behaves in date comparisons across the codebase. Ask which
   risk the user prefers. If they choose the setting change, the follow-up is: are they
   willing to have you audit the other `timezone.now().date()` call sites?
2. **Are there already `MembershipApplication` rows in production or on the dev database?**
   If yes, their `mandate_signed_on` may already be wrong on the affected rows, and the
   archived PDFs are frozen bytes that cannot be re-rendered. Ask what should happen: a
   one-off correcting data migration, a manual review, or leave them and note it.
3. **Should the PDF show the timezone explicitly** (e.g. "02.07.2026 um 00:30:15 Uhr
   (MESZ)")? For an evidence document this removes the ambiguity entirely and is worth
   doing regardless of the answer to question 1.

## Suggested fix (only after the questions are answered)

If the user chooses the local-conversion route:

* `membership_pdf.py`: `timezone.localtime(application.submitted_at).strftime(...)`, with an
  explicit timezone label if agreed in question 3.
* `membership_views.py`: `timezone.localdate(application.submitted_at)` for
  `mandate_signed_on`.

If the user chooses the settings change, do both of the above *anyway* — they are correct
either way and make the intent explicit at the point where it matters.

Check `_age_on()` and `update_mandate_view`'s `timezone.now().date()` while you are in there;
they have the same one-day-boundary property, with much lower stakes.

## Acceptance criteria

* A test that freezes time at 22:30 UTC on a summer day, submits an application, approves it,
  and asserts `mandate_signed_on` is the *following* calendar day (i.e. the German local
  date).
* A test asserting the string rendered into the PDF matches the local-time date.
* If the setting was changed: a note in `docs/` recording that storage stays UTC and only
  presentation is local.
