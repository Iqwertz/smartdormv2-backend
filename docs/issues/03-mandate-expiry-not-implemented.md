# 03 — The 36-month mandate expiry is documented everywhere and implemented nowhere

**Severity:** Critical (dormant) — no member can hit it yet, but every collection after it
should have been enforced is unauthorised.
**Area:** Mandate register
**Status:** open

---

## Instructions for the agent

Read this entire file first.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available. Whether an
expired mandate should block a collection silently or loudly is a decision for the
Finanzenreferat, not for you.

---

## What is wrong

`SEPA_MANDATE_EXPIRY_MONTHS = 36` in `smartdorm/config.py` (~line 76) is dead configuration.
Grep the whole repository: nothing reads it.

The rule it describes is real — under the SEPA Core Direct Debit scheme a mandate that has
not been used for 36 months lapses and must be obtained again. Three places in the code
assert that the system handles this:

* `smartdorm/config.py`: *"A SEPA mandate that has not been used for this many months expires
  and must be re-obtained."*
* `smartdorm/models.py`, `Membership.last_collection_on` help text: *"Entscheidet über
  FRST/RCUR und über den Ablauf des Mandats nach 36 Monaten ohne Nutzung."*
* `Membership.MandateStatus.EXPIRED` exists as a choice.

`MandateStatus.EXPIRED` is never assigned anywhere in the codebase. `is_collectable_on()`
checks only `mandate_status == ACTIVE`, so a mandate untouched for four years is still
collectable. The resulting debit is unauthorised, and the member has 13 months to reclaim it
under the SEPA rules — see `docs/membership_legal.md` section 5.4.

## Why it is wrong / how it got here

The config constant and the model docstring were written as part of the design, and the
enforcement was never wired up. Nothing fails or looks wrong today because the feature is
new — the earliest a membership could expire is 36 months after the first mandate is signed.
That is precisely why it needs to be fixed now rather than discovered later.

Note the subtlety in where the clock starts: for a member who has been collected before it
runs from `last_collection_on`; for a member who has *never* been collected it runs from
`mandate_signed_on`. Both fields exist on `Membership`.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/config.py` | `SEPA_MANDATE_EXPIRY_MONTHS` |
| `smartdorm/models.py` | `Membership.is_collectable_on`, `MandateStatus`, `last_collection_on`, `mandate_signed_on` |
| `smartdorm/views/membership_views.py` | `_collectable_memberships`, `preview_direct_debit_view`, `update_mandate_view` |
| `smartdorm/management/commands/` | where a periodic expiry job would live, if one is wanted |
| `smartdormv2-frontend/src/types/membership.ts` | `MandateStatus` already includes `"EXPIRED"` |
| `docs/membership_legal.md` | section 6 lists what the system guarantees |

## Questions to ask first

1. **Should expiry be computed on the fly, or written into `mandate_status`?**
   * On the fly (a check inside `is_collectable_on`) is always correct and needs no job, but
     the register never *shows* a mandate as expired until someone looks.
   * A management command that flips the status to `EXPIRED` makes it visible and reportable,
     but needs to be scheduled, and there is currently no scheduler in this project (see
     `docs/index.md`: asynchronous tasks are not implemented).
   * Ask which the user wants. Doing both — compute for correctness, flip for visibility — is
     also defensible.
2. **Should the member and/or the Finanzenreferat be warned before a mandate expires?** For
   example an email at 33 months. If yes, the same scheduling question applies.
3. **What should happen to an expired mandate operationally?** Is there a process for
   re-obtaining one, or does the member simply have to submit a new declaration? Note that
   issue 08 (a member cannot currently re-apply at all) may block whatever answer is given.
4. **Confirm the 36-month figure and the start date** with the Finanzenreferat, and confirm
   the clock runs from `last_collection_on` falling back to `mandate_signed_on`.

## Suggested fix (only after the questions are answered)

1. Add a helper on `Membership`, e.g. `mandate_expires_on`, returning
   `(last_collection_on or mandate_signed_on) + relativedelta(months=SEPA_MANDATE_EXPIRY_MONTHS)`.
2. Have `is_collectable_on(reference_date)` return `False` when `reference_date` is past that
   point. This is the part that actually prevents the unauthorised debit.
3. Surface it in `preview_direct_debit_view` as a named reason in the skipped list rather
   than an anonymous count (see issue 14), so the Finanzenreferat can see *why* someone
   dropped out of a run.
4. Implement the status flip and/or warning email only if the user asked for it in questions
   1 and 2.
5. If the answer is "compute on the fly only", delete nothing — but make sure the config
   comment and the `last_collection_on` help text describe what the code now actually does.

## Acceptance criteria

* A test with a membership whose last collection is 37 months old asserting it is not
  collectable.
* A test with a never-collected membership signed 37 months ago asserting the same.
* A test asserting a membership at 35 months *is* still collectable.
* `SEPA_MANDATE_EXPIRY_MONTHS` is read by production code, or removed.
