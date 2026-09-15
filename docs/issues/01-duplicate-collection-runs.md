# 01 — Nothing prevents generating the same collection twice

**Severity:** Critical — this is the one that can debit real members twice.
**Area:** SEPA collection (`pain.008` generation)
**Status:** open

---

## Instructions for the agent

Read this entire file before touching anything. This code moves money out of the bank
accounts of real people, so the bar for "I understood the problem" is higher than usual.

**Do not write or change any code until you have asked the user the questions in
*Questions to ask first* and received answers.** Use the `AskUserQuestion` tool if it is
available to you, otherwise ask in plain text and wait. The questions are not a formality:
each one changes what the correct fix looks like.

Once you have answers, implement the fix, and finish by adding the regression test named in
*Acceptance criteria*.

---

## What is wrong

`create_direct_debit_view` in `smartdorm/views/membership_views.py` (~line 710) does not
check whether a `DirectDebitRun` already exists for the requested `collection_date`. Calling
the endpoint twice with the same date produces two complete, valid `pain.008` files, and if
both are submitted to the bank every member is debited twice.

None of the existing constraints catch it:

* `DirectDebitRun.message_id` is unique, but the value comes from `sepaxml`'s
  `make_msg_id()` (`SepaDD.__init__` -> `shared.py`), which is random per instance. Two runs
  never collide on it.
* `DirectDebitItem`'s `unique_together = (('run', 'membership'))` only enforces uniqueness
  *within one run*. It says nothing about a second run.
* `Membership.last_collection_on` is written after each run, but `is_collectable_on()` never
  reads it. So on the second run the same members are collectable again — this time as
  `RCUR`, which looks perfectly normal to the bank.

The frontend (`smartdormv2-frontend/src/components/membership/DirectDebitDialog.tsx`) only
guards a double *click*: the button is disabled while `isCreating` is true, and `preview` is
cleared afterwards so `canCreate` goes false. That stops nothing that matters — a page
reload, a second finance officer, a second browser tab, or a direct API call all bypass it.

There is also a concurrency variant of the same bug: `_collectable_memberships()` reads
without `select_for_update()`, so two simultaneous requests both see the old
`last_collection_on` and both emit `FRST` for the same members.

## Why it is wrong / how it got here

The design deliberately split preview from create so that advancing the mandate sequence is
a conscious act — that reasoning is written into the docstring of
`preview_direct_debit_view`. The step that was missed is that "conscious act" and "act that
happened exactly once" are different properties. The uniqueness that does exist
(`message_id`, `unique_together`) was chosen to satisfy the bank's requirements, not to make
the operation idempotent for the Verein.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/views/membership_views.py` | `create_direct_debit_view`, `preview_direct_debit_view`, `_collectable_memberships` |
| `smartdorm/models.py` | `DirectDebitRun`, `DirectDebitItem`, `Membership.is_collectable_on` |
| `smartdorm/migrations/` | a new migration is needed for any constraint you add |
| `smartdormv2-frontend/src/components/membership/DirectDebitDialog.tsx` | where the error must be surfaced to the finance officer |
| `docs/membership_legal.md` | section 6 describes what the system claims to guarantee; update it if the guarantee changes |

## Questions to ask first

1. **Is more than one collection run per due date ever legitimate?** For example a
   correction run for a member who was missed, or a second file after the bank rejected the
   first. If yes, a hard unique constraint on `collection_date` is wrong and the guard has
   to be an explicit confirmation instead.
2. **If a duplicate is attempted, what should happen?** Refuse with an error naming the
   existing run, or return the existing run unchanged (idempotent), or allow it behind an
   explicit `confirm_duplicate` flag that the frontend has to set after showing a warning?
3. **Should the guard be scoped more tightly than the date** — e.g. one run per
   (collection_date, amount), so that a deliberate different-amount run is still possible?
4. **Is there existing production data** in `t_direct_debit_run`? If yes, a unique
   constraint migration may fail and you need to know what to do with pre-existing
   duplicates before adding it.

## Suggested fix (only after the questions are answered)

Assuming the common answer — one run per due date, refuse duplicates, allow an explicit
override:

1. Add a `UniqueConstraint` on `DirectDebitRun.collection_date` (or a partial one that
   excludes discarded runs, if issue 11 is being done at the same time) plus a migration.
2. In `create_direct_debit_view`, check for an existing run *before* building the file and
   return `409 Conflict` with the existing run's id, creation date and creator in the
   message. Keep the `IntegrityError` catch as the race-condition backstop — the check alone
   is not enough.
3. Wrap the collectable-membership read in `select_for_update()` so two concurrent creates
   serialise.
4. Surface the 409 in `DirectDebitDialog.tsx` as a distinct, clearly worded warning rather
   than the generic error string.

Do **not** silently deduplicate. A finance officer who tried to create a second run needs to
find out that a first one exists.

## Acceptance criteria

* A test asserting that two `create_direct_debit` calls for the same date result in exactly
  one `DirectDebitRun` and one set of `DirectDebitItem` rows.
* A test asserting `Membership.last_collection_on` is written exactly once.
* The frontend shows a comprehensible message when the second attempt is refused.
* `docs/membership_legal.md` section 6 mentions the guarantee if you added one.
