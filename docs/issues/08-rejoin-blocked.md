# 08 — A former member can never rejoin, and same-year rejoins collide on the mandate reference

**Severity:** Medium — a dead end with no workaround short of direct database access.
**Area:** Membership lifecycle
**Status:** open

---

## Instructions for the agent

Read this entire file first. The clean fix here is a schema change, so the questions matter
more than usual — a wrong guess means a migration you have to undo.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available.

---

## What is wrong

`Membership` is a `OneToOneField(primary_key=True)` on `Tenant` (`smartdorm/models.py`,
~line 715): **one membership row per tenant, ever**. Two guards then treat "a row exists" as
"is a member":

* `apply_for_membership_view` (~line 183): `if Membership.objects.filter(tenant=tenant).exists()`
  → *"Für dich ist bereits eine Mitgliedschaft hinterlegt."*
* `my_membership_status_view` (~line 100): returns `state: 'MEMBER'` for any existing row.

Neither looks at `ended_on`. So once the departure flow ends a membership
(`department_views.py` ~line 1037, `membership.end_membership(...)`), that person is
permanently locked out: the dashboard tells them they are a member, and the apply endpoint
refuses them. A resident who moves out and moves back in — which happens — cannot rejoin.

`docs/membership_legal.md` section 3 already notes there is no way to enter a membership
except direct DB access. This closes the last remaining door.

**Second, related defect:** `sepa_utils.build_mandate_reference` produces
`HSV-<join year>-<tenant id, 5 digits>`. Two memberships for the same tenant starting in the
same calendar year generate the identical reference. `decide_application_view` (~line 445)
catches the resulting `IntegrityError` and returns a 409 telling the member to contact the
Finanzenreferat — which is honest, but it is a dead end rather than a resolution. And SEPA
requires a mandate reference to be unique per creditor *permanently*, so reusing one after
deleting an old row would be worse than the collision.

## Why it is wrong / how it got here

`OneToOneField` models the common case exactly right — at any moment a tenant has at most one
membership — and it makes `tenant_id` a natural primary key that `DirectDebitItem` can point
at. What it cannot express is a *sequence* of memberships over time. The `ended_on` field was
added for the end-of-tenancy rule and the two ideas were never reconciled.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/models.py` | `Membership` (the `OneToOneField`), `is_active`, `end_membership`, `DirectDebitItem.membership` |
| `smartdorm/views/membership_views.py` | `my_membership_status_view`, `apply_for_membership_view`, `decide_application_view`, `list_members_view`, `reveal_iban_view`, `update_mandate_view` (all address a membership by `tenant_id`) |
| `smartdorm/utils/sepa_utils.py` | `build_mandate_reference` |
| `smartdorm/views/department_views.py` | ~line 1035, the departure hook |
| `smartdorm/serializers.py` | `MembershipSerializer` |
| `smartdormv2-frontend/src/services/membershipService.ts` and `src/components/membership/` | every URL is `/members/<tenant_id>/…` |
| `smartdorm/migrations/0015_*.py` | the existing schema |

## Questions to ask first

1. **How likely is a rejoin in practice, and is it worth a schema change?**
   * *Minimal fix:* keep `OneToOneField`, and change the two guards to ignore memberships
     where `ended_on` has passed — then overwrite the existing row on re-approval. Cheap, no
     migration, but it **destroys the previous membership's record**, which conflicts with
     the 8-year retention in `membership_legal.md` section 5.4.
   * *Proper fix:* `ForeignKey` instead of `OneToOne`, one row per membership period, with a
     partial unique constraint allowing only one open (`ended_on IS NULL`) membership per
     tenant. Migration touches `DirectDebitItem`'s FK and every `tenant_id`-addressed URL.
   * Ask which the user wants. Given retention requirements, recommend the proper fix — but
     let them decide, and be explicit that the minimal fix loses history.
2. **What should the mandate reference look like** so it is unique per creditor forever?
   Options: include the membership row id instead of the year, or append a sequence
   (`HSV-2026-00042-02`). Confirm the format with the Finanzenreferat, since it appears on
   members' bank statements and in the approval email. It must stay within 35 characters and
   the SEPA character set (`sepa_utils.sanitize_reference`).
3. **When a former member rejoins, is a new SEPA mandate required?** Almost certainly yes —
   the old mandate ended with the old membership. Confirm, because it decides whether the
   rejoin flow can copy the old bank details or must collect them afresh.
4. **What should `my_membership_status_view` return for a former member?** A distinct state
   (e.g. `FORMER_MEMBER`) so the frontend can offer "rejoin" rather than either hiding the
   option or pretending nothing happened? That needs a small frontend change too.
5. **Is `MembershipPrompt` (the opt-out) supposed to survive a rejoin?** Probably it should
   be cleared, or the returning resident will never be prompted again.

## Suggested fix (only after the questions are answered)

Implement the option chosen in question 1. If it is the `ForeignKey` route:

* Add an explicit `id` primary key, keep a partial `UniqueConstraint` on
  `(tenant)` where `ended_on IS NULL`.
* Repoint `DirectDebitItem.membership` and check every `get_object_or_404(..., tenant_id=…)`
  call site — they must resolve to the *open* membership, not an arbitrary one.
* Update `build_mandate_reference` per question 2.
* Add the new status to `my_membership_status_view` and to
  `smartdormv2-frontend/src/types/membership.ts`.

## Acceptance criteria

* A test where a tenant joins, the membership is ended, and the same tenant successfully
  applies and is approved again — with a *different* mandate reference.
* A test asserting the historical membership and its `DirectDebitItem` rows survive the
  rejoin.
* A test asserting a tenant with an open membership still cannot apply twice.
