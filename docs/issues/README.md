# Membership feature — known issues

Findings from a detailed review of the HSV membership implementation
(`docs/membership_legal.md` describes the feature itself). Each file in this folder is a
self-contained brief: what is wrong, why it is wrong, which files are involved, and what an
agent should ask before changing anything.

**Every file instructs the agent to ask the user clarifying questions before writing code.**
That is deliberate. Most of these are not "the code does X, it should do Y" — they are places
where the code made a choice, and only the Verein can say which choice was intended.

Not covered here: the authorization gap in `MEMBERSHIP_APPROVER_GROUPS` (see
`membership_legal.md` sections 4 and 5.1), which is being handled separately.

## Suggested order

Work top-down. Issue 01 is the one that can cost real money today.

| # | Issue | Severity |
|---|---|---|
| [01](./01-duplicate-collection-runs.md) | Nothing prevents generating the same collection twice | **Critical** |
| [02](./02-collection-run-input-validation.md) | The collection amount and due date are barely validated | **Critical** |
| [03](./03-mandate-expiry-not-implemented.md) | The 36-month mandate expiry is documented but not implemented | **Critical** (dormant) |
| [04](./04-timezone-utc.md) | `TIME_ZONE = 'UTC'` puts the wrong date on the SEPA mandate | High |
| [05](./05-mandate-signature-date-and-amendments.md) | Changing an IBAN rewrites the mandate signature date | High |
| [06](./06-unencrypted-declaration-pdf.md) | The declaration PDF stores the IBAN unencrypted | High |
| [07](./07-terms-version-not-reproducible.md) | `terms_version` alone does not reproduce the original wording | High |
| [08](./08-rejoin-blocked.md) | A former member can never rejoin | Medium |
| [09](./09-register-hides-active-members.md) | Members with a departure date vanish from the register | Medium |
| [10](./10-prenotification-email-reliability.md) | The pre-notification email can fail silently | Medium |
| [11](./11-run-lifecycle-and-rollback.md) | `last_collection_on` advances at generation, not submission | Medium |
| [12](./12-iban-access-audit-trail.md) | The IBAN audit trail is deleted after 30 days | Medium |
| [13](./13-tenant-resolution-by-username.md) | Tenants are resolved by a nullable, non-unique column | Medium |
| [14](./14-assorted-smaller-fixes.md) | Five smaller fixes (minor check, join date, skip reasons, …) | Low–Medium |
| [15](./15-membership-test-coverage.md) | The feature has no tests at all | Medium |

## Issues that are cheaper done together

* **01 + 11** — a run status field interacts with the duplicate-date constraint.
* **05 + 12** — both want a durable record of who touched payment data; one model can serve both.
* **03 + 08** — what happens to an expired mandate depends on whether re-joining is possible.
* **09 + 14d** — the same active-member arithmetic appears in the register and the preview.
* **15 + anything** — every other issue's acceptance criteria are tests.
