# 09 — Members with a departure date vanish from the register while still being debited

**Severity:** Medium — the register and the collection disagree about who is a member.
**Area:** Member register (UI/API consistency)
**Status:** open

---

## Instructions for the agent

Read this entire file first. This is a small fix, but confirm the intended semantics before
changing the filter — "active" means something specific to the Finanzenreferat.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available.

---

## What is wrong

`list_members_view` in `smartdorm/views/membership_views.py` (~line 522) defaults to:

```python
if not include_ended:
    queryset = queryset.filter(ended_on__isnull=True)
```

But `Membership.end_membership()` sets `ended_on = tenant.move_out`, and a move-out date is
normally in the **future** when the departure is closed. So the moment a departure is
processed, that member disappears from the default member register — even though they are
still a member for weeks or months and still owe contributions.

Meanwhile `is_collectable_on(reference_date)` correctly keeps them in the collection until
the due date passes, and its docstring explains exactly why that is right:

> a membership that ends on 30.09. still owes the contributions due before then

Both behaviours are individually defensible. Together they mean the Finanzenreferat sees N
members in the register and the collection preview charges N + k. The two screens disagree,
and the one that disagrees is the one people use to sanity-check the other.

`Membership.is_active` already implements the correct predicate —
`ended_on is None or ended_on >= today` — and `list_members_view` does not use it.

## Why it is wrong / how it got here

`ended_on__isnull=True` reads as "not ended" and is right for a field that is only ever set
in the past. Here it is set to a future date on purpose, which is the good part of the
design — that is what makes the final months collectable. The filter simply was not updated
to match.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/views/membership_views.py` | `list_members_view`, `preview_direct_debit_view` (`active_members` count, same problem) |
| `smartdorm/models.py` | `Membership.is_active`, `is_collectable_on`, `end_membership` |
| `smartdorm/views/department_views.py` | ~line 1037, where `ended_on` is set to `move_out` |
| `smartdorm/serializers.py` | `MembershipSerializer` already exposes `is_active` and `ended_on` |
| `smartdormv2-frontend/src/components/membership/` | the register grid and its `include_ended` toggle |

## Questions to ask first

1. **What should the default register view show?** Members who are active *today*
   (`ended_on is None or ended_on >= today`), or only members with no end date at all? The
   first matches `is_active` and the collection behaviour; ask to confirm that is what the
   Finanzenreferat expects.
2. **Should a member with a pending end date be visually marked** in the grid — e.g. "endet
   am 30.09.2026" — so it is obvious they are leaving but still being collected? The
   serializer already sends `ended_on`, so this may be frontend-only.
3. **Should the `include_ended=true` option stay as-is** (everything, including long-past
   memberships), or become a three-way filter: active / ending soon / ended?
4. **The same inconsistency exists in `preview_direct_debit_view`'s `skipped_members`
   count** — `active_members` there does not exclude tenants whose `move_out` has passed, so
   the "skipped" figure does not decompose into anything actionable. Ask whether to fix it
   here or as part of issue 14, which proposes replacing the bare count with per-member
   reasons.

## Suggested fix (only after the questions are answered)

Assuming the expected answer to question 1:

```python
today = timezone.now().date()
if not include_ended:
    queryset = queryset.filter(Q(ended_on__isnull=True) | Q(ended_on__gte=today))
```

Keep it consistent with `Membership.is_active` — ideally derive both from one place so they
cannot drift again. Then apply whatever was agreed for questions 2–4.

## Acceptance criteria

* A test asserting a membership with `ended_on` one month in the future appears in the
  default register listing.
* A test asserting a membership that ended last month does not.
* A test asserting the register count and the collection preview count agree for the same
  reference date, given identical data.
