# 06 — The declaration PDF stores the full IBAN unencrypted next to the encrypted one

**Severity:** High — defeats the stated purpose of the field encryption.
**Area:** Data protection / storage
**Status:** open

---

## Instructions for the agent

Read this entire file first.

**Do not change any code until you have asked the user the questions in *Questions to ask
first* and received answers.** Use the `AskUserQuestion` tool if available. The migration
strategy for existing rows is the part you must not improvise.

---

## What is wrong

`MembershipApplication.declaration_pdf` (`smartdorm/models.py`, ~line 690) is a plain
`BinaryField`. The PDF it holds prints the member's full IBAN — deliberately, and correctly:
`membership_pdf.render_declaration_pdf` documents that *"the full IBAN is printed: this
document is the mandate itself, and a mandate without the account number proves nothing."*

The IBAN is also stored in `iban_ciphertext`, Fernet-encrypted via
`smartdorm/utils/crypto_utils.py`. The stated threat model for that encryption is written at
the top of `crypto_utils.py` and repeated in `docs/membership_legal.md` section 6:

> this defends against a leaked database dump or an old backup.

It does not, as long as the PDF sits in the same table. Every `pg_dump` of
`t_membership_application` contains `declaration_pdf` with the account number in cleartext.
An attacker who obtains a dump extracts the PDFs and reads every IBAN without needing
`FIELD_ENCRYPTION_KEYS` at all. The encryption of `iban_ciphertext` buys nothing against the
exact threat it was built for.

Note what is *not* wrong: the decision to keep the PDF in the database rather than
`MEDIA_ROOT` is sound, and the reasoning in the field's `help_text` is right. Serving it
through the permission-checked `application_pdf_view` rather than the webserver is also
right. The gap is only that the blob itself is not encrypted.

## Why it is wrong / how it got here

Two good decisions were made independently — "encrypt the IBAN column" and "archive the
declaration as a PDF blob so it cannot be served statically" — and the interaction between
them was not considered. This is a very typical seam bug: neither change is wrong on its own.

## Relevant files

| File | What to look at |
|---|---|
| `smartdorm/models.py` | `MembershipApplication.declaration_pdf`, `EncryptedIbanMixin` |
| `smartdorm/utils/crypto_utils.py` | `encrypt_str` / `decrypt_str` (they take and return `str`, so bytes need base64) |
| `smartdorm/views/membership_views.py` | `apply_for_membership_view` (writes it), `application_pdf_view` (reads it) |
| `smartdorm/utils/membership_pdf.py` | `render_declaration_pdf` returns raw bytes |
| `smartdorm/serializers.py` | `MembershipApplicationSerializer.get_has_pdf` |
| `docs/membership_legal.md` | sections 6 and 7 — the claims that need to become true |

## Questions to ask first

1. **Are there existing applications with stored PDFs**, on production or on the dev
   database? If yes, a data migration must encrypt them in place, and that migration needs
   `FIELD_ENCRYPTION_KEYS` to be available when it runs. Ask how the user wants to sequence
   that, and whether a backup is taken first.
2. **What should happen if a stored PDF cannot be decrypted** (key rotated away, per section
   7 of `membership_legal.md`)? `crypto_utils.decrypt_str` deliberately raises rather than
   returning garbage. Should `application_pdf_view` return a clear 500 explaining the key
   problem — the way `reveal_iban_view` already does — or fall back to something else?
3. **Should the same treatment apply to the email attachment?** The PDF is currently sent to
   the applicant by email (`_send_submission_emails`), which means the full IBAN travels over
   SMTP in cleartext. The applicant is the data subject and it is their own IBAN, so this is
   defensible — but ask whether the Verein wants to keep doing it, or send a masked copy and
   let the member download the full one from the portal.
4. **Is encrypting the blob enough, or should the PDF be regenerable instead?** An
   alternative design is to not store the PDF at all and re-render on demand — but that is
   blocked by issue 07 (the terms cannot currently be reproduced faithfully), so the storage
   route is almost certainly right. Confirm.

## Suggested fix (only after the questions are answered)

1. Base64-encode the PDF bytes and run them through `crypto_utils.encrypt_str` before saving;
   reverse on read in `application_pdf_view`. Keep the field a `BinaryField` (storing the
   token as bytes) or move to a `TextField` — either is fine, but a migration is needed
   either way.
2. Add a data migration that encrypts existing rows, guarded so it fails loudly if
   `FIELD_ENCRYPTION_KEYS` is unset rather than corrupting data.
3. Handle `DecryptionFailed` in `application_pdf_view` per the answer to question 2.
4. Update `docs/membership_legal.md` section 6 — the honest caveat there ("schützt
   Datenbank-Dumps und Backups") only becomes accurate once this is done.

## Acceptance criteria

* A test asserting the raw column value for a stored declaration does **not** contain the
  IBAN in any form (search the raw bytes for the IBAN string and for its base64 encoding).
* A test asserting `application_pdf_view` still returns a valid, readable PDF.
* The data migration is idempotent, or refuses to run twice.
