# 15 — The membership feature has no tests at all

**Severity:** Medium — but it is the multiplier on every other issue in this folder.
**Area:** Test coverage
**Status:** open

---

## Instructions for the agent

Read this entire file first.

**Do not write any tests until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available. How the existing
suite is run and against which database is something you must not guess at — see question 1,
and note that the repository's `run-tests.sh` and `pytest.ini` are the starting point.

---

## What is wrong

`smartdorm/tests/` contains `integration/test_api.py`, `integration/test_db_integrity.py`
and `integration/test_db_integrity_full.py`. None of them mention membership, SEPA, mandates
or direct debits — `grep -rn "embership" smartdorm/tests/` returns nothing.

So the following are all currently unverified by any automated check:

* that an application can only be submitted once while open;
* that the minor check actually blocks anyone;
* that an approval produces a unique, SEPA-conformant mandate reference;
* that `FRST` is emitted once and `RCUR` thereafter;
* that a member whose membership ended is excluded from the right runs and included in the
  right ones;
* that the generated `pain.008` validates against the schema at all;
* that an IBAN never appears in any list response;
* that the amount in the XML equals the amount recorded in the database.

That last group is the point. This feature's correctness properties are unusually
*checkable* — they are arithmetic and state machines, not judgement calls — and none of them
are being checked.

## Why it is wrong / how it got here

The feature was built end-to-end in one pass, and the existing test suite is
integration-style and database-dependent, which raises the cost of adding the first test.
That cost is worth paying once here: nearly every other issue in this folder ends with an
acceptance criterion that is a test, and they will all be much cheaper to satisfy once the
scaffolding exists.

## Relevant files

| File | What to look at |
|---|---|
| `pytest.ini`, `run-tests.sh` | how the suite is configured and invoked |
| `smartdorm/tests/integration/` | existing style, fixtures, database handling |
| `smartdorm/management/commands/generate_demo_data.py` | already builds membership demo data — likely reusable as fixtures |
| `smartdorm/views/membership_views.py`, `smartdorm/utils/sepa_utils.py`, `smartdorm/utils/crypto_utils.py`, `smartdorm/models.py` | the code under test |
| `.venv/lib/python3.13/site-packages/sepaxml/validation.py` | `export(validate=True)` already validates against the schema — lean on it |

## Questions to ask first

1. **How is the suite run, and against what database?** There is a note in the project memory
   that the system `node` is unusable and that `.venv/bin/python` plus nvm v22 are the
   correct toolchain, and that checks against the dev database need care. Confirm with the
   user how to run tests safely before running anything — do not point a test runner at a
   database with real member data.
2. **Unit tests with fixtures, or integration tests in the existing style?** The existing
   suite is integration-flavoured and `Tenant` is `managed = False`, which complicates
   fixture creation. Ask which the user prefers, and whether adding `pytest-django` fixtures
   or a factory library is acceptable.
3. **Which behaviours matter most to cover first?** Recommend, in order: (a) no duplicate
   collection run, (b) FRST/RCUR correctness across two runs, (c) the amount in the XML
   equals the amount in the database, (d) no endpoint ever returns an unmasked IBAN except
   `reveal_iban_view`. Ask whether the user agrees or wants a different order.
4. **Should tests generate a real `pain.008` and validate it?** `sepaxml` can validate against
   the schema; doing so requires filling `HSV_CREDITOR_ID` / `IBAN` / `BIC` with test values
   via `override_settings` or a config fixture. Ask whether that is acceptable — it is the
   single highest-value test in the feature, and note that `check_creditor_config` currently
   refuses any ID starting with `DE00ZZZ`, so the test value must be a plausible one.
5. **Is there appetite for a `FIELD_ENCRYPTION_KEYS` test key?** Several paths cannot be
   tested without one. A fixed throwaway key in the test settings is normal practice;
   confirm the user is comfortable with one living in the repository.

## Suggested fix (only after the questions are answered)

Build the smallest scaffolding that lets a test create a tenant, submit an application,
approve it, and generate a run — then write the four tests from question 3. Do not attempt
exhaustive coverage in one pass; the goal is to make the *next* test cheap.

Where an issue in this folder is fixed, its acceptance-criteria test belongs here rather than
in a separate file.

## Acceptance criteria

* `run-tests.sh` (or the agreed command) runs the new tests green, without touching any
  database holding real member data.
* At minimum the four behaviours from question 3 are covered.
* A short note in `docs/` or in this file recording how to run the membership tests.
