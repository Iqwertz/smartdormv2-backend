# 05 — Changing a member's IBAN rewrites the mandate signature date

**Severity:** High — falsifies a fact in the mandate register and breaks the SEPA amendment
rules.
**Area:** Mandate register
**Status:** open

---

## Instructions for the agent

Read this entire file first.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available. Question 1 in
particular determines the whole shape of the fix, and getting it wrong means writing a
migration twice.

---

## What is wrong

`update_mandate_view` in `smartdorm/views/membership_views.py` (~line 592) does this when the
Finanzenreferat corrects a member's bank details:

```python
if data.get('iban'):
    membership.set_iban(data['iban'])
    membership.last_collection_on = None
    membership.mandate_signed_on = timezone.now().date()
    changes.append('IBAN (Mandatssequenz auf FRST zurückgesetzt)')
```

Resetting `last_collection_on` so the next collection goes out as `FRST` is **correct** — the
new account has never been debited under this mandate. The problem is
`mandate_signed_on = today`. Two separate things are wrong with it:

1. **It records something that did not happen.** The member signed the mandate on the
   original date. Nobody signed anything today; a finance officer typed a new account number.
   After this edit the mandate register contradicts the archived declaration PDF, which is
   the document the Verein would produce in a dispute. The entire versioned-terms and
   archived-PDF design (`membership_texts.py`, `membership_pdf.py`) exists to keep those two
   in agreement.

2. **It is not how SEPA handles an account change.** Changing the debtor account is an
   *amendment* to the existing mandate, not a new mandate. The rules expect the original
   mandate ID and the original signature date to be retained, with the amendment signalled in
   the transaction (`AmdmntInd` set, and the previous account carried in `OrgnlDbtrAcct`).
   Here the mandate ID is kept but the date silently moves and no amendment information is
   emitted at all — so the bank sees an existing mandate ID suddenly claiming a different
   signature date.

There is a second, related gap in the same endpoint: the only record of the change is a
`logger.info` line. There is no stored history of what the IBAN was changed from and to, no
reason field, and no notification to the member. A finance officer can silently redirect a
member's mandate at any account, and (see issue 12) the log line is deleted after 30 days.

## Why it is wrong / how it got here

`mandate_signed_on`'s help text says *"Datum der Mandatserteilung — geht so in die pain.008
ein"*, which is right. The reset was almost certainly added alongside the `FRST` reset out of
a reasonable instinct that "this is effectively a fresh mandate for a fresh account". For the
*sequence type* that instinct is correct; for the *signature date* it is not, because that
date refers to a signature, and a signature has a real date that the Verein cannot move.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/views/membership_views.py` | `update_mandate_view` |
| `smartdorm/serializers.py` | `MembershipMandateUpdateSerializer` |
| `smartdorm/models.py` | `Membership.mandate_signed_on`, `mandate_reference`, `mandate_status` |
| `smartdorm/utils/sepa_utils.py` | `build_direct_debit_xml` — where `mandate_date` is emitted |
| `smartdorm/utils/membership_pdf.py` | the archived document this must stay consistent with |
| `.venv/lib/python3.13/site-packages/sepaxml/debit.py` | check whether `sepaxml` supports amendment fields before promising them |
| `docs/membership_legal.md` | sections 5.1 and 6 |

## Questions to ask first

1. **When a member changes bank, does the Verein obtain a new signed mandate, or amend the
   existing one?** This is the crux.
   * *New mandate* — then a new mandate reference and a new signature date are both correct,
     but they need a new signed declaration to point at, and the old mandate should be
     recorded as ended rather than overwritten. This probably needs a mandate history table.
   * *Amendment* — then keep the original reference and date, reset to `FRST`, and emit the
     amendment fields. Check `sepaxml` supports them; it may not, in which case the user
     needs to know that limitation before choosing.
   * Ask what the Finanzenreferat actually does in practice today.
2. **Who is allowed to change an IBAN, and on what evidence?** Should the endpoint require a
   mandatory free-text reason ("member sent new details by email on 3.9.") that gets stored?
3. **Should the member be emailed when their bank details change?** This is a meaningful
   fraud control and costs one template.
4. **Do you want a `MembershipMandateChange` history table** (who, when, old last4, new
   last4, old/new status, reason), or is an append-only log sufficient? Note that issue 12
   covers the same underlying gap for IBAN *reveals*, so the two may want to share one model
   — ask whether to design them together.
5. **Are there existing rows whose `mandate_signed_on` has already been overwritten?** If so,
   can the original be recovered from `application.submitted_at`, and should a data migration
   do that?

## Suggested fix (only after the questions are answered)

Minimum, valid under either answer to question 1: stop writing `mandate_signed_on = today` as
a side effect of an IBAN edit. Keep the `FRST` reset.

Beyond that, implement whichever of the two models the user chose, and add the history
record and member notification if they asked for them. If they chose "amendment" and
`sepaxml` cannot emit `AmdmntInd`, say so explicitly rather than shipping something that
looks compliant and is not.

## Acceptance criteria

* A test asserting an IBAN change leaves `mandate_signed_on` untouched.
* A test asserting an IBAN change sets `last_collection_on = None` so the next run is `FRST`.
* A test asserting the mandate date in a generated `pain.008` equals the date printed in the
  archived declaration PDF for the same member.
* If a history table was added: a test asserting a change writes exactly one row with the old
  and new masked IBAN.
