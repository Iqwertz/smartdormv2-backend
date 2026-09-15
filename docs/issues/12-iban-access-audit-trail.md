# 12 — The IBAN access audit trail is a log file that gets deleted after 30 days

**Severity:** Medium — the system promises attributable access to payment data and cannot
deliver it.
**Area:** Data protection / auditability
**Status:** open

---

## Instructions for the agent

Read this entire file first. If issue 05 is also being worked on, read it too — both want a
durable record of who touched payment data, and one model can serve both.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available.

---

## What is wrong

`reveal_iban_view` (`smartdorm/views/membership_views.py`, ~line 540) records every reveal
like this:

```python
logger.info("User '%s' revealed the IBAN of member %s (%s).",
            request.user.username, tenant_id, membership.tenant.get_full_name())
```

That is the *entire* audit trail. Three things undermine it:

1. **It is a plain file.** `LOGGING` in `smartdorm/settings.py` (~line 239) uses a
   `logging.FileHandler` writing to `logs/smartdorm.log` — no rotation, no integrity
   protection, no structure.
2. **It is deleted on a schedule.** `smartdorm/management/commands/cleanup_old_logs.py`
   removes log entries older than `--days`, default **30**.
3. **The retention horizons it is supposed to serve are years long.**
   `docs/membership_legal.md` section 5.4 works in 8 years (§ 147 AO) and 13 months (SEPA
   chargeback window).

Meanwhile the system makes an explicit promise in section 6:

> jedes Aufdecken wird mit dem handelnden Benutzer protokolliert

and the privacy notice shown to the member in `membership_texts.py` makes the same promise.
A record that evaporates in 30 days does not keep it. If a member asks in March who looked at
their bank details in January, there is no answer.

The same applies to `application_pdf_view` (the PDF contains the full IBAN) and to
`download_direct_debit_view` (the XML contains every member's IBAN) — both log and nothing
more. The collection download is arguably the most sensitive access of all, since it exposes
the whole register at once.

## Why it is wrong / how it got here

`logger.info` is the natural way to record something in this codebase, and for most of
SmartDorm it is entirely appropriate. The membership feature inherited the pattern without
noticing that here the log line is not diagnostics — it is a compliance artefact with a
defined retention requirement, and it is subject to a cleanup job written for diagnostics.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/views/membership_views.py` | `reveal_iban_view`, `application_pdf_view`, `download_direct_debit_view`, `update_mandate_view` |
| `smartdorm/settings.py` | `LOGGING`, the `file` handler |
| `smartdorm/management/commands/cleanup_old_logs.py` | the 30-day deletion |
| `smartdorm/models.py` | where an audit model would go |
| `smartdorm/membership_texts.py` | `privacy_notice` / `sepa_privacy_notice` — the promise made to the member |
| `docs/membership_legal.md` | sections 5.1, 5.4 and 6 |

## Questions to ask first

1. **Which accesses should be recorded?** IBAN reveal is the obvious one. Ask whether to also
   record declaration-PDF downloads and collection-file downloads — recommend yes for both,
   especially the collection file.
2. **How long should audit rows be kept, and who decides?** Section 5.4 says the retention
   question is to be settled with the Steuerberater and that no automatic deletion job was
   implemented on purpose. The same reasoning probably applies here: store indefinitely,
   delete manually. Confirm rather than assume.
3. **Should the record include a reason?** Requiring the approver to state why they are
   revealing an IBAN is a strong control and a small UI change. Ask whether that is
   proportionate for a Verein of this size or just friction.
4. **Should a member be able to see who accessed their data?** Art. 15 DSGVO gives them the
   right to ask; a self-service view is optional but makes the promise in the privacy notice
   concrete.
5. **Share one model with the mandate-change history from issue 05, or keep two?** A single
   `MembershipAuditEvent` with an event type covers reveals, downloads and mandate changes.
   Ask which the user prefers before designing the schema.
6. **Should `cleanup_old_logs` be changed?** Even with a database audit trail, silently
   deleting application logs after 30 days may be shorter than the user realises. Worth
   raising while you are here, but it is their call.

## Suggested fix (only after the questions are answered)

1. Add an audit model (shape per questions 1 and 5) with at least: timestamp, acting
   username, event type, target tenant/membership, and optionally a reason and the request IP.
2. Write a row in the same transaction as each access it covers. Keep the `logger.info` calls
   too — they cost nothing and help during debugging.
3. Expose a finance-only listing of audit events, since a record nobody can read is only
   marginally better than none.
4. Update `docs/membership_legal.md` section 6 so the claim matches the implementation.

## Acceptance criteria

* A test asserting a successful IBAN reveal writes exactly one audit row naming the acting
  user and the target member.
* A test asserting a *failed* reveal (decryption error, missing IBAN) is also recorded — a
  failed attempt is as interesting as a successful one.
* A test asserting audit rows survive `cleanup_old_logs`.
