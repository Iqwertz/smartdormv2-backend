# 02 — The collection amount and due date are barely validated

**Severity:** Critical — a typo currently becomes a five-figure direct debit.
**Area:** SEPA collection (`pain.008` generation)
**Status:** open

---

## Instructions for the agent

Read this entire file first. Both defects live in the same function, so fix them together.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available. The pre-
notification question in particular is a legal question about the mandate text, not a
technical preference — you must not guess at it.

---

## What is wrong

`_parse_run_request` in `smartdorm/views/membership_views.py` (~line 636) accepts an amount
and a due date from the request body with almost no checking.

### 2a — Amount

```python
amount = Decimal(str(raw_amount)) if raw_amount is not None else _fee()
...
if amount <= 0:
    raise ValueError('Der Betrag muss größer als 0 sein.')
```

* The amount is a free-text `TextField` on the frontend (`DirectDebitDialog.tsx`), so
  whatever the user types arrives here as a string.
* `Decimal("1e5")` parses successfully to `Decimal('1E+5')` — one hundred thousand. It is
  greater than zero, it fits `amount_per_member`'s `max_digits=10`, and it debits every
  member 100 000 EUR. A plain mistyped `"1000"` passes just as easily, with no confirmation
  step anywhere.
* There is no upper bound at all, and no comparison against `HSV_MEMBERSHIP_FEE_EUR`.
* There is no `quantize`. `Decimal('10.005')` reaches
  `sepa_utils.build_direct_debit_xml` (~line 111), where
  `int((Decimal(amount) * 100).to_integral_value())` uses banker's rounding and produces
  1000 cents = 10.00 EUR in the XML — while `DirectDebitRun.amount_per_member`, a
  `DecimalField(decimal_places=2)`, stores 10.01 on the Postgres side. The stored record then
  disagrees with what the bank actually collected, which is exactly the kind of discrepancy
  that is impossible to reconstruct a year later.

### 2b — Due date

`collection_date` is parsed with `date.fromisoformat` and then used as-is. It is never
checked against:

* **Today.** A run due yesterday is generated happily; the bank rejects the whole file.
* **The pre-notification period.** `docs/membership_legal.md` section 2 and the mandate text
  in `membership_texts.py` (key `sepa_prenotification`) promise the member at least
  `HSV_PRENOTIFICATION_DAYS` (currently 5) calendar days' notice. Nothing stops a run due
  tomorrow. That shortened period is the *only* reason the statutory 14 days does not apply,
  so violating it undermines the agreement it rests on.
* **TARGET business days.** A due date on a weekend or a TARGET holiday is not a valid
  settlement date.

## Why it is wrong / how it got here

The amount field exists so the Verein can collect something other than the standard monthly
fee (arrears, a changed Beitragsordnung). That is a reasonable feature — but an open text
field that reaches `Decimal()` unchecked treats "any number the user typed" as "a number the
user meant". `HSV_PRENOTIFICATION_DAYS` and `HSV_COLLECTION_DAY` exist in `config.py` but are
only ever interpolated into display text (`membership_texts.get_terms`, the approval email);
no code path treats them as rules.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/views/membership_views.py` | `_parse_run_request`, `preview_direct_debit_view`, `create_direct_debit_view` |
| `smartdorm/utils/sepa_utils.py` | `build_direct_debit_xml`, the cents conversion |
| `smartdorm/config.py` | `HSV_MEMBERSHIP_FEE_EUR`, `HSV_PRENOTIFICATION_DAYS`, `HSV_COLLECTION_DAY` |
| `smartdorm/membership_texts.py` | key `sepa_prenotification` — the promise being made |
| `smartdormv2-frontend/src/components/membership/DirectDebitDialog.tsx` | the amount input and date picker |
| `docs/membership_legal.md` | section 2 |

## Questions to ask first

1. **What is a plausible upper bound for the amount per member?** The standard fee is
   10.00 EUR/month. Should a run above e.g. 50 EUR be refused outright, or allowed behind an
   explicit confirmation? Is collecting several months at once a real use case?
2. **Should the due date be enforced against `HSV_PRENOTIFICATION_DAYS`, or only warned
   about?** Enforcing it means the Finanzenreferat cannot do a rushed collection even when
   they want to. Warning means the promise in the mandate text can be broken by clicking
   through. Ask which the Verein wants — and whether the pre-notification clock starts at the
   approval email or somewhere else (see issue 10).
3. **Should a due date in the past be refused?** It is always a mistake, but confirm there is
   no back-dating workflow you would break.
4. **Do you want TARGET business-day validation?** It needs a holiday calendar (e.g. the
   `holidays` package, or a small hard-coded TARGET list — TARGET closes on New Year, Good
   Friday, Easter Monday, 1 May, 25 and 26 December). Ask whether adding a dependency is
   acceptable, or whether nudging the date to the next business day automatically is
   preferred over refusing.
5. **When the amount differs from `HSV_MEMBERSHIP_FEE_EUR`, should the UI warn** that a fresh
   pre-notification to all members is legally required and is a manual step? (Section 2 of
   `membership_legal.md` says it is.)

## Suggested fix (only after the questions are answered)

1. In `_parse_run_request`, quantize the amount explicitly:
   `Decimal(str(raw_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)` — and reject
   input that is not a plain decimal string, so `"1e5"` and `"inf"` never reach `Decimal`.
   Bound it against the limit agreed in question 1.
2. Validate `collection_date` per the answers to questions 2–4. Put the check in
   `_parse_run_request` so preview and create behave identically — the preview must not show
   a run that create would refuse.
3. In `sepa_utils.build_direct_debit_xml`, make the cents conversion explicit about rounding
   rather than relying on `to_integral_value`'s default, or assert the amount is already
   quantized before converting.
4. Consider constraining the frontend input too (numeric field, step 0.01, max), but treat
   that as cosmetic — the server check is the real one.

## Acceptance criteria

* A test asserting `"1e5"` is refused.
* A test asserting the amount stored on `DirectDebitRun` equals the amount in the generated
  XML, cent for cent.
* A test asserting a due date inside the pre-notification window is handled per the answer to
  question 2.
* Preview and create agree: any input create refuses, preview also refuses.
