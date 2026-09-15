# 10 — The pre-notification email can fail silently, and emails are sent inside transactions

**Severity:** Medium — a member can be debited without ever having been notified, with no
record that it happened.
**Area:** Notification / legal obligation
**Status:** open

---

## Instructions for the agent

Read this entire file first.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available. Question 1 is a
legal question about what the Verein has committed to — do not decide it yourself.

---

## What is wrong

### 10a — Nobody checks whether the pre-notification was delivered

`email_utils.send_email_message` catches every exception and returns `False`
(`smartdorm/utils/email_utils.py`, ~line 74):

```python
except Exception as e:
    logger.error(f"Failed to send email to {recipient_list} ...", exc_info=True)
    return False
```

No caller in `membership_views.py` inspects the return value. That is defensible for the
"your application was received" mail. It is not defensible for the **approval** mail
(`email/tenant-membership-approval.html`), because per `docs/membership_legal.md` section 2
that single email *is* the pre-notification for every future collection, and it is where the
member is told their mandate reference — a promise made explicitly in section 6:

> Sie wird dem Mitglied in der Aufnahme-E-Mail mitgeteilt, also vor dem ersten Einzug.

If that mail bounces (wrong address, mail server down, template error), the approval still
succeeds, the mandate goes `ACTIVE`, the member is collected on the next run — and no state
anywhere records that they were never notified. Nothing retries, nothing warns, and the only
trace is a log line that is deleted after 30 days (see issue 12).

### 10b — Emails are sent inside `@transaction.atomic`

`apply_for_membership_view` and `decide_application_view` are both decorated
`@transaction.atomic` and call `send_email_message` inside the block. If anything rolls the
transaction back after the send, the member holds a welcome email quoting a mandate reference
that does not exist in the database. Django's `transaction.on_commit()` exists for exactly
this.

## Why it is wrong / how it got here

`send_email_message` is a shared utility used across all of SmartDorm, where "log it and
carry on" is the right behaviour — a failed parcel notification should not break a parcel.
The membership feature reuses it without noticing that here one of the emails carries a legal
obligation rather than a convenience.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/utils/email_utils.py` | `send_email_message` and its return contract |
| `smartdorm/views/membership_views.py` | `decide_application_view`, `apply_for_membership_view`, `_send_submission_emails` |
| `smartdorm/templates/email/tenant-membership-approval.html` | the pre-notification itself |
| `smartdorm/models.py` | `Membership` — where a `notified_at` field would go |
| `docs/membership_legal.md` | sections 2 and 6 |

## Questions to ask first

1. **If the approval email fails, what should happen?**
   * Fail the whole approval and ask the approver to retry? (Safest, but the approver may not
     be able to fix a broken mailbox.)
   * Approve anyway, but record `approval_notified_at = NULL` and block or warn on the next
     collection for that member?
   * Approve anyway and only surface a warning in the register?
   * Ask the user — this is the Verein's call about their own obligation.
2. **Should the collection preview refuse or flag members who were never notified?** This is
   the control that actually prevents an un-notified debit. Recommend it, but confirm.
3. **Should there be a "resend approval email" action** for the Finanzenreferat, and should
   it update the notification timestamp?
4. **Is a one-time pre-notification the final decision?** `membership_legal.md` section 2
   leaves this open — the alternative is a notification before every single collection, which
   is not implemented. Ask whether it has since been decided, because it changes what a
   `notified_at` field should mean.
5. **Should the same treatment apply to the rejection email?** Lower stakes, but a member who
   is never told their application was rejected is also a problem.

## Suggested fix (only after the questions are answered)

1. Add a nullable `approval_notified_at` (and possibly `approval_notification_error`) to
   `Membership`, written from the return value of `send_email_message`.
2. Move all `send_email_message` calls in the membership views into
   `transaction.on_commit(lambda: ...)` so nothing is sent for a transaction that rolls back.
   This part is safe to do regardless of the answers above.
3. Implement whichever behaviour was chosen in questions 1–3 — most likely: approve, record
   the failure, and show un-notified members prominently in both the register and the
   collection preview.

## Acceptance criteria

* A test where the mail backend raises, asserting the approval outcome matches the answer to
  question 1 and that the failure is recorded in the database, not only in the log.
* A test asserting no email is sent when the surrounding transaction rolls back.
* If flagging was chosen: a test asserting an un-notified member is visible as such in the
  collection preview.
