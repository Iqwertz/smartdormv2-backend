# 07 — `terms_version` alone does not reproduce the original wording

**Severity:** High — the versioning system does not deliver the guarantee it was built for.
**Area:** Evidence / versioned terms
**Status:** open

---

## Instructions for the agent

Read this entire file first.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available.

---

## What is wrong

`membership_texts.get_terms()` (`smartdorm/membership_texts.py`, ~line 151) pulls an
immutable, dated text block out of `MEMBERSHIP_TERMS` — and then interpolates values from the
**current** `config.py` into it:

```python
placeholders = {
    'fee': str(app_config.HSV_MEMBERSHIP_FEE_EUR).replace('.', ','),
    'creditor_id': app_config.HSV_CREDITOR_ID,
    'creditor_name': app_config.HSV_CREDITOR_NAME,
    'creditor_address': app_config.HSV_CREDITOR_ADDRESS,
    'collection_day': app_config.HSV_COLLECTION_DAY,
    'prenotification_days': app_config.HSV_PRENOTIFICATION_DAYS,
}
```

The dict is versioned. The values substituted into it are not. Raise the fee from 10 to 12
EUR and `get_terms('2026-09-01')` renders the 2026 declaration text asserting a 12,00 EUR
monthly contribution — which is not what that member agreed to.

This contradicts the module's own docstring (*"the Verein must be able to show the text that
was on screen when they clicked submit"*) and `docs/membership_legal.md` section 6 (*"sodass
ein Antrag von 2026 auch 2031 im Originalwortlaut rekonstruierbar ist"*).

**What partly saves it:** the PDF is rendered once at submission and stored as frozen bytes,
so for applications with a stored PDF the original wording *is* preserved.

**Why that is not enough:** `apply_for_membership_view` (~line 229) deliberately tolerates a
failed PDF render —

```python
except Exception:
    # The application itself is valid and recorded; a missing archive copy must not
    # discard it. It is regenerable from the stored data and terms version.
```

— and that comment is not true. For any row where the render failed, the original wording is
unrecoverable, because the fee and creditor ID would be re-interpolated from whatever
`config.py` says at the time of regeneration. `application_pdf_view` currently returns 404
for those rows rather than regenerating, so nothing produces a *wrong* document today; the
evidence simply does not exist.

There is also a latent crash: `value.format(**placeholders)` is applied to every string in
the terms dict, so any future terms text containing a literal `{` or `}` raises at render
time — including in the tenant-facing `membership_terms_view`.

## Why it is wrong / how it got here

Two correct instincts pulling in opposite directions: "never repeat the fee in six places"
(so put it in config) and "never let the agreed text change" (so version the text). The
config values are the join between them, and they inherited the mutability of config rather
than the immutability of the terms.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/membership_texts.py` | `get_terms`, `MEMBERSHIP_TERMS`, `CURRENT_TERMS_VERSION` |
| `smartdorm/config.py` | `HSV_MEMBERSHIP_FEE_EUR`, `HSV_CREDITOR_ID`, `HSV_COLLECTION_DAY`, `HSV_PRENOTIFICATION_DAYS` |
| `smartdorm/models.py` | `MembershipApplication` — where snapshot fields would go |
| `smartdorm/views/membership_views.py` | `apply_for_membership_view`, `membership_terms_view`, `application_pdf_view` |
| `smartdorm/utils/membership_pdf.py` | `render_declaration_pdf` — the consumer of `get_terms(version)` |
| `docs/membership_legal.md` | section 6, "Beweisfähigkeit" |

## Questions to ask first

1. **Snapshot the values onto the application, or freeze them inside the versioned terms
   dict?**
   * *Snapshot fields* (`fee_at_submission`, `creditor_id_at_submission`, …) on
     `MembershipApplication`, passed into `get_terms` at render time. Needs a migration;
     keeps `config.py` as the single place to edit going forward.
   * *Freeze in the dict*: each dated version carries its own literal fee and creditor ID, so
     `config.py` only supplies values for the *current* version. No migration; but changing
     the fee then means adding a new terms version, which is arguably correct anyway.
   * Ask which the user prefers — and note that changing the fee legally requires a new
     pre-notification to all members regardless (`membership_legal.md` section 2), so a new
     terms version is not an unreasonable price.
2. **Should a failed PDF render still allow the application to be recorded?** The current
   trade-off (keep the application, lose the archive copy) was a deliberate choice. Given
   the archive copy is the evidence, ask whether the user would now rather fail the
   submission and ask the member to retry, or keep the current behaviour and add an alert so
   somebody notices and can regenerate it the same day.
3. **Should `application_pdf_view` be able to regenerate a missing PDF?** It only becomes
   safe once question 1 is fixed. Ask whether it is wanted, and whether a regenerated
   document should be visibly marked as regenerated.
4. **Are there existing applications with a NULL `declaration_pdf`?** If yes, decide what to
   do about them before anything else.

## Suggested fix (only after the questions are answered)

Implement whichever option from question 1 the user chose. Then, independently of that:

* Replace `value.format(**placeholders)` with something that tolerates stray braces —
  `string.Template` with `$fee`-style placeholders, or `str.format_map` over pre-escaped
  text. Whatever you pick, add a test with a terms string containing a literal `{`.
* Fix the misleading comment in `apply_for_membership_view` so it states what is actually
  true.
* Update `docs/membership_legal.md` section 6 to match reality.

## Acceptance criteria

* A test that submits an application, changes `HSV_MEMBERSHIP_FEE_EUR`, re-renders the terms
  for that application's version, and asserts the **original** fee appears.
* A test asserting a terms string containing `{` renders without raising.
* No production code path can render an old terms version with current config values.
