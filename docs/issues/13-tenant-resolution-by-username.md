# 13 — A membership is attached to a tenant resolved by a nullable, non-unique column

**Severity:** Medium — low likelihood, but the failure mode is attaching a SEPA mandate to
the wrong person.
**Area:** Identity resolution
**Status:** open

---

## Instructions for the agent

Read this entire file first. Start by establishing whether the problem is real *in this
database* — question 1 is an investigation, not a preference.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available.

---

## What is wrong

Every tenant-facing membership endpoint resolves the acting person through this helper
(`smartdorm/views/membership_views.py`, ~line 56):

```python
def _get_tenant(request):
    """The Tenant behind the logged-in account, or None for non-tenant accounts."""
    return Tenant.objects.filter(username=request.user.username).first()
```

`Tenant.username` (`smartdorm/models.py`, ~line 38) is
`models.CharField(max_length=255, null=True, blank=True)` on a table declared
`managed = False`. There is no unique constraint in the model, and the table is owned by an
upstream system, so the model is not the authority on what the database permits.

`.filter(...).first()` with no `order_by` means: if two `Tenant` rows ever share a username,
which one is returned is **whatever the database happens to hand back first**, and it can
differ between requests on the same data.

What that resolves is not a display name. It is the tenant a Beitrittserklärung is filed
under, the tenant a `Membership` and its SEPA mandate are attached to, and the tenant whose
`birthday` gates the minor check. The obvious scenario is a resident who moves out and later
returns, if the upstream system creates a second row rather than reusing the first — the same
scenario that issue 08 is about.

A second, quieter variant: `request.user.username` for a non-tenant account (an admin, a
service account) could in principle match a `Tenant` row with a coincidentally equal
username, and there is no cross-check against employee type.

## Why it is wrong / how it got here

`t_tenant` comes from LDAP-backed upstream data (`smartdorm/utils/ldap_sync.py`), so Django
cannot impose a constraint on it and `managed = False` is correct. Matching on username is
the only join available. The gap is that the code treats a lookup that *may* be ambiguous as
one that cannot be, and stays silent when it is.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/views/membership_views.py` | `_get_tenant` and all five call sites |
| `smartdorm/models.py` | `Tenant` (`managed = False`, nullable `username`) |
| `smartdorm/utils/ldap_sync.py` | how tenants and usernames are created and updated |
| other views | `grep -rn "Tenant.objects.filter(username" smartdorm/` — the same pattern likely exists elsewhere |
| `../smartdormv2-db/` | the actual schema; check whether a unique index exists at the DB level |

## Questions to ask first

1. **Does the database actually allow duplicate usernames?** Check `smartdormv2-db` and the
   live schema for a unique index on `t_tenant.username`, and run a count of duplicates on
   the dev database. Report what you find before proposing anything — if a unique constraint
   already exists upstream, this issue reduces to defensive logging.
2. **What does the upstream system do when a former resident returns?** Reuse the existing
   `t_tenant` row, or create a new one? This is the deciding fact. Ask the user; they may
   need to check with whoever owns the tenant data.
3. **If a duplicate is ever detected, what should happen?** Refuse the membership action with
   a clear error and alert the Referat, or pick deterministically (e.g. the row with the
   latest `move_in`, or the one whose tenancy covers today) and log a warning? Refusing is
   safer for a financial action; picking is friendlier for read-only ones.
4. **Should `_get_tenant` also verify the account is a tenant account** rather than staff?
   `permissions.HasUserTypePermission` reads employee type from `request.user.first_name`
   (the LDAP mapping). Ask whether adding that check is wanted, or whether it would lock out
   legitimate cases.
5. **Should this be fixed only for membership, or everywhere the pattern occurs?** Membership
   is where the consequences are financial, but a shared helper would fix the rest too.

## Suggested fix (only after the questions are answered)

Depending on the findings:

* At minimum, make the ambiguity impossible to miss: count the matches, log an `error` when
  it is greater than one, and handle it per the answer to question 3 — never silently
  `.first()`.
* Add an explicit deterministic `order_by` so behaviour is at least reproducible.
* If the database permits duplicates and the upstream owner agrees they should not exist,
  a unique index upstream is the real fix; the application-side check remains as a guard.
* Consider recording the resolved `tenant_id` alongside `submitted_by_username` on
  `MembershipApplication` — it already stores the username, and storing both makes any future
  mismatch detectable after the fact.

## Acceptance criteria

* A documented answer to question 1, written into this file or into `docs/database_schema.md`.
* A test with two `Tenant` rows sharing a username asserting the behaviour agreed in question
  3 — not an arbitrary pick.
* No membership code path silently resolves an ambiguous username.
