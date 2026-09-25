# Todo

Open bugs, cleanups, projects and ideas for the backend. Frontend items live in the
frontend repo's `docs/todo.md`.

**How to use this file:** add an item when you find something you're not fixing right now.
Say where it is, what goes wrong, and what the fix should be if that's already decided.
Tick items off instead of deleting them, and add the date and commit. Clear out ticked items
once a semester.

## Bugs

- [ ] **Move-out confirmation mail says "Hallo {'Name'},".**
  [tenant_views.py:350](../smartdorm/views/tenant_views.py) passes `{tenant.name}`, which is a
  Python set, as `greeting`. It has been like this since 2973608. Fix: `tenant.name`.
- [ ] **The rejection mail is missing a date.** `tenant-extension-rejection.html` uses
  `{{departureDate0}}` ("… wird die Verwaltung das Zimmer zum {{departureDate0}} an einen neuen
  Mieter vergeben"), but `process_claim_decision_view` only passes `departureDate`,
  `departureDate1` and `departureDate2`, so the sentence ends with an empty date. Decide which
  date is meant and pass it.
- [ ] **Former tenants keep their LDAP groups.** The nightly `recalculate_tenant_stats` only
  reconciles *current* tenants, so after moving out, people keep their floor, Referat, HSV
  and default groups (wlan, wiki, Bewohner, tenant).
  *Decided (2026-09-25):* the account stays, but after the move-out date it loses **all**
  groups and roles, including manual `LdapRoleAssignment`s. Subtenants whose sublets have
  all ended are already handled this way in the subtenant phase of the sync.
- [ ] **The semester switch doesn't undo LDAP changes it already made.**
  `update_semester_and_ldap_view` rolls back the database when one LDAP call fails, but the
  group changes made before that failure stay. The next nightly sync repairs this, because
  `current_semester` is unchanged, but until then some people have the wrong groups.
- [ ] **The Pi scan endpoints are public.** `GET /api/printing/active-session/` and
  `POST /api/printing/scans/` need no login, so anyone who can reach the API can see
  the active session id and upload a file into someone's print session. Move them behind
  `HasDeviceToken`, like the agent endpoints (the Pi agent must send the token too).
- [ ] **Hand-set move-out dates don't last.** Editing a tenant's `move_out`, approving a claim
  with `move_out_date`, or closing a departure with `move_out_date` writes the date directly.
  The next `recalculate_tenant_contract_dates()` (e.g. when a subtenant is added) overwrites it
  without warning. Either turn such dates into a Verwaltung extension automatically, or warn
  in the frontend. See [domain/contract-dates.md](domain/contract-dates.md).
- [ ] **The integration test is probably broken.** `tests/integration/test_api.py` requests `/`,
  which has no route. The integration tests also need a test database, which can't be
  built from the `managed=False` legacy tables. Fix or delete them.

- [x] **The password reset revealed which emails have an account.** Found and unknown addresses
  got different success texts. Both now say the same (2026-09-25, API message translation).

## Projects

- [ ] **Bring the access-rule rewrite to production.** It is merged into `development`
  (e51f53c) but not into `main`. Before deploying, check the production LDAP groups against
  `permissions.Groups`: the dev data says ADMIN members are `TENANT` accounts and the office
  account is `DEPARTMENT` in `VERWALTUNG`.
- [ ] **Review the logs for past abuse.** Until September 2026 almost every endpoint was open
  to any logged-in account. This included a tenant → any-LDAP-account takeover through the
  writable `TenantSerializer.username` + resend credentials.

## Cleanup

- [ ] Remove `_ensure_signatures_for_all_confirmed_departures()` and its call in
  `create_and_notify_departure_signatures()` (`utils/helper.py`). It is a "temporary
  migration step" for departures from SmartDorm v1, which has been shut down.
- [ ] Delete the unused email templates: `department-info-ex-tenants`,
  `management-partner-university-confirmation`, `tenant-partner-university-confirmation`,
  `tenant-personal-account`, `test-template-button`. Check the Git history for why they
  exist first.
- [ ] Delete the dead constants `VERWALTUNG_ADMIN_GROUPS`, `DEPARTMENT_EMPLOYEE_TYPE`
  (`department_views.py`) and `HEIMRAT_INFO_GROUPS` (`engagement_views.py`).
- [ ] `run-server.sh` runs `makemigrations` on every start, so migrations can get generated
  (and committed) by accident. Only run `migrate` there.
- [ ] `GET /api/tenants/calendar-proxy/` (Nextcloud calendar) isn't used by the frontend: the
  calendar widget reads `api-rooms.schollheim.net` directly. Remove it, or switch the widget back.
- [ ] Six `print()` calls in views and utils should use the module logger.
- [ ] Move the 8-month window for departure candidates into `config.py`
  (`list_departure_candidates_view`).
- [ ] `delete_department_view` fails with a 500 when the department still has engagements.
  Check first and return a clear error.
- [ ] `recalculate_tenant_contract_dates` only logs changes bigger than 3 days ("temp change,
  remove when stable"). Decide whether that's still needed.
- [ ] `device_overview_view` has a TODO to check that the user is in the device's
  responsible department. Right now any Verwaltung member may manage every device.
- [ ] New ids for legacy tables are `max(id) + 1`, set by hand. Two requests at the same
  time can collide. That's rare at our traffic, but a Postgres sequence per table
  would fix it for good.

## Ideas

(none yet)
