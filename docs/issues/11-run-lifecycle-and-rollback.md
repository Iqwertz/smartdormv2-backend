# 11 — `last_collection_on` advances when the file is generated, not when it is submitted

**Severity:** Medium — an unsubmitted or rejected run corrupts the mandate sequence with no
way back.
**Area:** SEPA collection lifecycle
**Status:** open

---

## Instructions for the agent

Read this entire file first. If issue 01 is also being worked on, read that one too — a run
status field interacts with the duplicate-run constraint proposed there, and doing both at
once is cheaper than doing them in sequence.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available.

---

## What is wrong

`create_direct_debit_view` (`smartdorm/views/membership_views.py`, ~line 768) ends with:

```python
# Advance the sequence so the next run for these members goes out as RCUR.
Membership.objects.filter(
    tenant_id__in=[item['membership'].tenant_id for item in items]
).update(last_collection_on=collection_date)
```

This marks every included member as collected the moment the **file is generated** — not
when it is submitted to the bank, and not when the bank accepts it. A `DirectDebitRun` has no
status: it exists, and that is all the system knows about it.

So if the file is generated and then never uploaded, or is uploaded and rejected wholesale,
or the finance officer decides the date was wrong and simply closes the tab:

* every included member is flagged as having been collected;
* the next real run goes out as `RCUR` for members whose `FRST` never actually happened;
* there is no way to void the run and restore the previous `last_collection_on`.

Recovery today means editing `t_membership` by hand, and the information needed to do that
correctly — each member's *previous* `last_collection_on` — was overwritten and is gone.

## Why it is wrong / how it got here

The docstring is explicit about the reasoning: *"Persisting it, rather than regenerating on
download, is what keeps FRST/RCUR honest: the run records that these members have now been
collected once."* That is the right instinct — the sequence must be recorded somewhere
durable. What is missing is that generating a file and collecting money are two different
events separated by a manual step in the online banking, and only the first one is
observable to this system.

Note the raw material for a fix already exists: `DirectDebitItem` stores the membership,
mandate reference, sequence type and amount for every position in every run. What it does not
store is the value that was overwritten.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/models.py` | `DirectDebitRun`, `DirectDebitItem`, `Membership.last_collection_on`, `sequence_type` |
| `smartdorm/views/membership_views.py` | `create_direct_debit_view`, `list_direct_debit_runs_view`, `download_direct_debit_view` |
| `smartdorm/serializers.py` | `DirectDebitRunSerializer` |
| `smartdormv2-frontend/src/components/membership/DirectDebitDialog.tsx` and the runs list | where a status and a discard action would surface |
| `docs/membership_legal.md` | section 6, the FRST/RCUR claim |

## Questions to ask first

1. **What is the real-world workflow after the file is generated?** Does the finance officer
   upload it to the online banking the same day? Is there a confirmation from the bank that
   could be recorded? Understanding the actual sequence of human steps decides how many
   states the model needs.
2. **What states should a run have?** A minimal useful set is
   `GENERATED → SUBMITTED | DISCARDED`. Ask whether a `REJECTED` state (bank refused the
   file) and a per-item `RETURNED` state (individual chargeback, R-transaction) are wanted
   now or later. Chargebacks are a real recurring event — a member's account is overdrawn and
   the debit comes back — and the system currently has nowhere to record one at all.
3. **Should discarding a run restore `last_collection_on`?** To do that, each
   `DirectDebitItem` must store the *previous* value at generation time. Ask whether to add
   that field, since it means a migration.
4. **Who may discard a run, and for how long?** Only the creator? Only before it has been
   marked submitted? Never after 24 hours?
5. **Should the sequence advance at generation or at "mark as submitted"?** Deferring it is
   more truthful, but leaves a window where two runs would both emit `FRST` — which is why
   the current code advances early. Ask which risk the user prefers; combining the deferral
   with the duplicate guard from issue 01 removes the conflict.

## Suggested fix (only after the questions are answered)

Assuming the common answers:

1. Add `status` to `DirectDebitRun` with the states agreed in question 2, plus
   `submitted_at` / `discarded_at` / `discarded_by`.
2. Add `previous_last_collection_on` to `DirectDebitItem`, written at generation.
3. Add a discard endpoint (finance-only) that sets the run to `DISCARDED` and restores each
   item's `previous_last_collection_on` in one transaction.
4. Exclude discarded runs from the duplicate-date constraint in issue 01, so a discarded run
   can legitimately be replaced by a corrected one.
5. Show the status in the runs list, and make the download of a discarded run either blocked
   or clearly marked.

## Acceptance criteria

* A test that creates a run, discards it, and asserts every affected `Membership` has exactly
  the `last_collection_on` it had before — including `None` for first-time members.
* A test asserting a member whose only run was discarded is `FRST` again on the next run.
* A test asserting a discarded run does not block creating a new run for the same date.
