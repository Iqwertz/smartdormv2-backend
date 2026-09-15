# 14 — Assorted smaller fixes

**Severity:** Low to Medium — none of these alone is dangerous; several are one-line fixes
with real consequences.
**Area:** Mixed
**Status:** open

---

## Instructions for the agent

Read this entire file first. These are five independent items grouped only because each is
small. Treat them as five separate changes — do not bundle them into one commit if the user
would rather review them apart.

**Do not change any code until you have asked the user the questions below and received
answers.** Use the `AskUserQuestion` tool if available. You may ask about all five at once;
each item lists its own question(s).

---

## 14a — The minor check is bypassed when `birthday` is NULL

**Where:** `smartdorm/views/membership_views.py` ~line 123 (`my_membership_status_view`) and
~line 198 (`apply_for_membership_view`).

```python
age = _age_on(tenant.birthday)
if age is not None and age < MINIMUM_AGE:
```

`_age_on` returns `None` when `birthday` is falsy, and `age is not None and ...` then reads
as **eligible**. The check fails open.

`Tenant.birthday` is declared `models.DateField()` (non-null) — but `Tenant` is
`managed = False`, so the model does not constrain the table and is not evidence about what
the data contains. The only other signal is `is_of_age`, which the create serializer
validates — and that is a self-declaration the client fully controls, which is exactly the
weakness `docs/membership_legal.md` section 3 was written to fix. If `birthday` is missing,
nothing verified anything.

**Questions:** Should a missing birthday block the online join (fail closed) and point the
person at the Finanzenreferat, the way an under-18 result does? Or is there a legitimate
population of tenants with no birthday on file who must not be locked out? Check the dev
database for NULL birthdays before asking, and bring the number to the conversation.

---

## 14b — `join_date` is unvalidated on approval

**Where:** `smartdorm/views/membership_views.py` ~line 403–412 (`decide_application_view`).

The comment above the code says:

> The approver may correct the requested date; otherwise the member's wish stands,
> but never earlier than the day the Verein actually admitted them.

The clause after "but" is not implemented. `join_date` is parsed from the request with
`date.fromisoformat` and used as-is, so an approver can set any date at all — including one
before the applicant's `move_in`, or years in the past, which implies retroactive
contributions the member never agreed to. `requested_join_date` from the applicant is equally
unbounded (the serializer only checks it is a date).

Note this also feeds `build_mandate_reference`, which embeds `join_date.year` — see issue 08.

**Questions:** What are the real bounds? Candidates: not before `tenant.move_in`, not before
the application's `submitted_at`, not more than N months in the future. Ask which the Verein
wants, and whether an approver should be able to override with an explicit reason. Also ask
whether the comment or the code is the intended behaviour — it is possible backdating is
wanted and the comment is simply stale.

---

## 14c — Approval does not re-verify the mandate

**Where:** `smartdorm/views/membership_views.py` ~line 420–440 (`decide_application_view`).

Approval sets `mandate_status = ACTIVE` and copies `iban_ciphertext` / `iban_last4` from the
application whenever `payment_method == SEPA`. It never rechecks that
`application.mandate_confirmed` is true or that an IBAN is actually present.

Today `MembershipApplicationCreateSerializer.validate` enforces both, so no application can
reach approval without them — this is defence in depth, not a live bug. It is worth having
because approval is the single transition that creates a debitable mandate, and because a
future path that creates applications another way (an admin entry form, a data import, the
paper-form route `membership_legal.md` section 3 asks for) would bypass the serializer
entirely.

**Question:** Add the guard, returning a clear error if an application marked SEPA lacks a
confirmed mandate or an IBAN? Recommend yes; it costs three lines.

---

## 14d — `skipped_members` is an unactionable number

**Where:** `smartdorm/views/membership_views.py` ~line 686–695
(`preview_direct_debit_view`).

```python
active_members = Membership.objects.filter(
    Q(ended_on__isnull=True) | Q(ended_on__gte=collection_date)
).count()
skipped = active_members - len(memberships)
```

Two problems. The arithmetic is inconsistent — `active_members` does not apply the
`tenant__move_out__lt` exclusion that `_collectable_memberships` does, and it counts members
on the `OTHER` payment method who were never candidates. And more importantly, a bare count
tells the finance officer nothing: "3 skipped" could mean three people on bank transfer, or
three revoked mandates, or three people whose mandate expired (issue 03) and who should have
been chased weeks ago.

This is the screen where money movement is authorised. It should say *who* dropped out and
*why*.

**Question:** Replace the count with a per-member list of skip reasons (no mandate / revoked /
expired / moved out / membership ended / no IBAN)? Should the frontend show it expanded by
default or behind a disclosure?

---

## 14e — The generated file is handed over via `window.open` after an `await`

**Where:** `smartdormv2-frontend/src/components/membership/DirectDebitDialog.tsx`, in
`handleCreate`.

```ts
const response = await createDirectDebit(...);
showNotification(response.message, "success");
window.open(directDebitXmlUrl(response.run.id), "_blank");
```

A `window.open` that is not in the synchronous part of a user-gesture handler is blocked by
default in most browsers. The run *was* created and is downloadable from the runs list, so
nothing is lost — but the primary path silently does nothing, and the user is left unsure
whether the run happened. Given issue 01 (nothing prevents a duplicate run), a user who is
unsure whether it worked and tries again is exactly the sequence that causes a double debit.

**Question:** Replace the popup with a visible download link in the success state, or trigger
the download via a hidden anchor click? Confirm the preferred UX before changing it.

---

## Relevant files (all items)

| File | Items |
|---|---|
| `smartdorm/views/membership_views.py` | 14a, 14b, 14c, 14d |
| `smartdorm/serializers.py` | 14b (`requested_join_date`), 14c |
| `smartdorm/models.py` | 14a (`Tenant.birthday`, `managed = False`) |
| `smartdormv2-frontend/src/components/membership/DirectDebitDialog.tsx` | 14d, 14e |
| `docs/membership_legal.md` | 14a relates to section 3 |

## Acceptance criteria

* 14a: a test with a tenant whose `birthday` is NULL asserting the agreed behaviour.
* 14b: a test asserting an out-of-bounds `join_date` is refused, and the stale comment either
  removed or made true.
* 14c: a test asserting an application marked SEPA without a confirmed mandate cannot be
  approved.
* 14d: the preview response lists a reason per skipped member; the numbers add up.
* 14e: the generated file is reachable without relying on a popup.
