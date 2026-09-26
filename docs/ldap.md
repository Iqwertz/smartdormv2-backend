# LDAP: accounts and groups

The dorm's OpenLDAP is the single source of truth for accounts, passwords and group
memberships. The same accounts log into SmartDorm, the WLAN (`schollroam`), the wiki and
other dorm services, so a wrong group change here is felt far beyond SmartDorm.

| | Production | Test / dev |
| --- | --- | --- |
| Server | `ldap.schollheim.net` | `ldap-test.schollheim.net` |
| Setting | `LDAP_URI`, bind as `cn=admin,dc=schollheim,dc=net` (`LDAP_ADMIN_PASSWORD`) | same |

## Directory layout

```text
dc=schollheim,dc=net
├── ou=users     accounts: cn=<username>
├── ou=groups    service groups: wlan, wiki, …
├── ou=groups2   dorm groups: Bewohner, HSV, floors (H1L3…), Referate (Barreferat…), Flursprecher-<floor>
└── ou=roles     roles: tenant, ADMIN, VERWALTUNG, …
```

Groups are `groupOfNames` with `member: cn=<user>,ou=users,…`. The layout grew with other
services, which is why there are three group OUs.

## Accounts

Created by `ldap_utils.create_ldap_user()`: `inetOrgPerson` + `sambaSamAccount`, with
`cn`, `sn`, `givenName`, `displayName`, `mail`, `employeeType`, a random `uid` and `sambaSID`,
and the password twice: `userPassword` (SSHA) and `sambaNTPassword` (NT hash, for WLAN
login). The server's OpenSSL has no MD4, so the NT hash is computed by a pure-Python MD4
in `ldap_utils.py`. **Every password change must write both attributes**
(`update_ldap_password()`).

| Kind | Username | employeeType | Default groups |
| --- | --- | --- | --- |
| Tenant | `j.mueller` (initial + surname) | `TENANT` | `tenant` (roles), `wlan`, `wiki`, `Bewohner`, own floor |
| Subtenant | `jonasmueller` (name + surname) | `SUBTENANT` | `wlan`, `wiki`, main tenant's floor |
| Verwaltung | – (existing account) | `DEPARTMENT` | `VERWALTUNG` |

Default groups are `DEFAULT_TENANT_LDAP_GROUPS` / `DEFAULT_SUBTENANT_LDAP_GROUPS` in
`config.py`. Never mutate those lists; copy them (`list(...)`) before appending.

**LDAP only stores hashes.** "Resending credentials" always means setting a new password
(`credential_utils.resend_credentials()`). If the mail can't be sent, the old hashes are
restored, so nobody is locked out. The self-service reset (`/api/auth/password-reset/`) finds
the account by `mail`, which is why tenant edits also sync the mail to LDAP.

## Login and group mirroring

`django-auth-ldap` binds as the user, maps `employeeType` → `user.first_name`, `sn` →
`last_name`, `mail` → `email`, and copies the user's group names (`cn`) from all three OUs into
Django groups (`AUTH_LDAP_MIRROR_GROUPS`). **This only happens at login**, and sessions last up
to two weeks. After a group change, the person must log out and back in.

## What changes groups

| Event | Change |
| --- | --- |
| Tenant created | defaults + floor |
| Room move / rental deleted | old floor group → new one, for the tenant and their running subtenants |
| Engagement created/deleted **in the current semester** | Referat group + `HSV` added/removed |
| Semester switch (Heimrat) | old semester's Referat groups removed, new ones added |
| Subtenant created | defaults + floor. A returning subtenant's account is reused. |
| Manual role (Netzwerkreferat page) | any group, optionally with an expiry date |
| Nightly sync | reconciles everything below |

A Referat's group name is the first word of `Department.full_name`, with umlauts spelled out
(`Barreferat (Technik)` → `Barreferat`). Flursprecher get `Flursprecher-<floor>`. See
[domain/engagements.md](domain/engagements.md).

## The nightly sync

`manage.py recalculate_tenant_stats` runs every night at 04:00 (cron, installed by
`deploy.sh`, output in `logs/cron.log`). `--dry-run` reports what would change without saving
stats, writing LDAP or deleting expired role records.

1. **Stats** for current tenants: `current_points` (sum of compensated engagements),
   `sublet` (months of all sublets, rounded to 0.5), `extension` (approved claims).
2. **Expired manual roles** (`LdapRoleAssignment.expires_at` in the past) are removed from LDAP
   and deleted.
3. **Current tenants:** the groups they *should* have = defaults + floor + (if they have an
   engagement this semester) `HSV` + their Referat groups + valid manual roles. Missing ones
   are added. Extra ones are removed **only if they are managed groups**.
4. **Subtenants**, matched by email among `SUBTENANT` accounts: a running sublet → defaults +
   floor. All sublets over → managed groups removed. Not started yet → untouched.

**Managed groups** are the only groups the sync may remove: the tenant defaults, `HSV`,
every floor group (taken from `t_room`, so empty floors are included), every Referat group,
and every `Flursprecher-<floor>`. Anything else (ADMIN, VERWALTUNG, service groups someone
added by hand) is never removed. That's the safety net: SmartDorm only takes away what it
hands out.

**Manual roles** (`LdapRoleAssignment`, `/api/network/ldap-roles/`) exist because of that
sync. Without a record, a hand-granted managed group would be stripped by the next morning.
The record makes the group "owed". It is keyed by username, not tenant, so it also works
for subtenants and the Verwaltung.

**Gap:** former tenants aren't processed, so they keep their groups. Decided: the account
stays and loses all groups after moving out. Tracked in [todo.md](todo.md).

## Useful commands

```bash
# all attributes of one account
ldapsearch -x -LLL -H ldap://ldap-test.schollheim.net:389 \
  -D "cn=admin,dc=schollheim,dc=net" -W -b "dc=schollheim,dc=net" "(cn=username)" \* +

# all groups in groups2
ldapsearch -x -LLL -H ldap://ldap-test.schollheim.net:389 \
  -D "cn=admin,dc=schollheim,dc=net" -W -b "ou=groups2,dc=schollheim,dc=net" \
  "(objectClass=groupOfNames)" cn
```

Use `ldap-test` unless you really mean production.
