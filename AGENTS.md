# SmartDorm backend

SmartDorm is the tenant management software of the Schollheim, a self-governed student dorm.
The students run the dorm themselves through elected *Referate*, and they earn points for
it. Two full-time employees, the *Verwaltung*, handle leases, money and legal matters.
SmartDorm covers both sides. The Verwaltung uses it to manage tenants, subtenants, moves,
move-outs, extensions and parcels. The residents use it for their profile, Referat
applications, points, printing and attendance at assemblies. It also keeps everyone's
accounts in the dorm's LDAP in sync (WLAN, wiki, group mailing lists).

This repo is the Django REST API. The React frontend is the sibling repo
`../smartdormv2-frontend`.

**Before doing anything, read [`docs/README.md`](docs/README.md).** It indexes what we
know about the domain, the architecture and operations, so you don't have to rediscover it
from the code.

## Stack

- Python 3 / Django 4.2 / Django REST Framework, a single app `smartdorm/`. Views are functions
  with `@api_view`.
- PostgreSQL. Most tables are legacy `t_*` tables from SmartDorm v1 (`managed = False`).
- LDAP (`django-auth-ldap` + `python-ldap`) is the identity source. Groups are mirrored into Django at login.
- Redis for sessions and caches. SMTP (IONOS) for mail. ReportLab/pypdf for PDFs.
- Deployed with GitLab CI to VMs (Gunicorn + Nginx). A cron job runs the nightly sync.

## Commands

Run everything from the repo root with the venv's Python. There is no system `python`.

```sh
set -a; source .env; set +a      # always first: without it manage.py silently uses a local DB
echo $DB_HOST                    # confirm which database you are about to touch
.venv/bin/python manage.py check
.venv/bin/python manage.py test smartdorm.tests.test_access smartdorm.tests.test_dev_accounts   # fast, no DB
.venv/bin/python manage.py list_api_access            # who may call which endpoint
./run-server.sh                                        # dev server on :8000 (see docs/development.md first)
```

The dev database is remote and holds real data. More in [`docs/development.md`](docs/development.md).

## Where things are

```text
smartdorm/models.py          all models (legacy t_* tables + Django-managed ones)
smartdorm/views/*_views.py   endpoints, one module per area (tenant, department, engagement, …)
smartdorm/urls.py            all routes
smartdorm/permissions.py     access rules; every view declares exactly one
smartdorm/config.py          domain constants (contract lengths, default LDAP groups, …)
smartdorm/utils/             LDAP, mail, PDF, CUPS, contract-date helpers
smartdorm/management/commands/  nightly sync, dev accounts, verification tools
smartdorm/templates/email/   mail templates (German, "du")
docs/                        knowledge base; docs/todo.md = open bugs and projects
```

## Rules

- **Look for an existing feature before building a new one.** If something similar already
  exists (an endpoint, a button, a flow), check whether it can be extended or combined
  instead of adding a parallel solution. If it's unclear, ask first how it should be done.
  Two features that do nearly the same thing confuse the Verwaltung and the residents.
- **Every endpoint declares exactly one access rule** from `permissions.py`. The startup check
  `smartdorm.E001` enforces it. Access changes need the snapshot regenerated
  (`list_api_access --write-snapshot`) and matching `requiredGroups` in the frontend.
  See [`docs/permissions.md`](docs/permissions.md).
- **Prefer columns over tables.** If new data belongs to one existing thing (a tenant, a
  room, a global setting), add a column to that table. Create a table only for a new thing
  that exists many times per parent (print jobs, attendance records). Legacy tables are
  `managed = False`, so a column is added with a raw-SQL migration, and it must be nullable
  or have a SQL default, because legacy rows won't have it. Never rename, drop or retype a
  legacy column. See [`docs/architecture.md`](docs/architecture.md#changing-the-database).
- **Database first, LDAP last.** LDAP writes can't be rolled back. Save the rows, do LDAP
  at the end, and roll the rows back if LDAP fails.
- **Contract dates are derived.** Never set `move_out` directly for a lasting change. Use a
  Verwaltung extension or a termination and let `recalculate_tenant_contract_dates()` do the
  rest. See [`docs/domain/contract-dates.md`](docs/domain/contract-dates.md).
- **Domain constants go in `config.py`**, not inline in views.
- **User-facing text is German and uses "du"** (lowercase mid-sentence, as grammar has it;
  short forms like "Bewohner", no ":innen"): emails, and every `error`/`message`/`detail`
  an endpoint returns, since the frontend shows them as they are. DRF's own 403/404/CSRF texts
  are translated in `smartdorm/exceptions.py`. Exception: responses only a machine reads
  (the Pi agent and scan endpoints) stay English.
  Keep it short and friendly, the way a fellow resident would write it. The email templates
  are the reference. The full guide is `../smartdormv2-frontend/docs/voice-and-tone.md`.
  Logs and code comments stay in English.
- **Outside production, every mail goes to `DEVELOPER_EMAIL`.** Never set `PRODUCTION=True`
  on a dev machine or the test server.
- **The dev DB and the test LDAP hold real data.** Wrap experimental writes in
  `transaction.atomic()` and raise to roll back. Never run `makemigrations` just to "see
  what happens"; only commit migrations you meant to write.
- Don't build point-based benefits (extensions, room upgrades) into the code. The
  Zimmerreferat and the Verwaltung decide those by hand.

## Keeping the docs alive

- **Update the docs in the same change as the code.** When you learn how something works or
  why, put it in the matching doc. If no doc fits, create one and add it to
  `docs/README.md`.
- **Record lasting instructions.** When the user gives an instruction that should outlive
  this task ("always…", "never…", "the Verwaltung wants…"), add it to the Rules above or the
  matching doc. Say in your reply that you did.
- **Decisions and their reasons** go into [`docs/decisions.md`](docs/decisions.md).
- **Bugs and ideas you're not fixing now** go into [`docs/todo.md`](docs/todo.md).
- **Things you couldn't verify** go into [`docs/open-questions.md`](docs/open-questions.md).
  Don't guess.

## Git

- `development` deploys to the test server automatically on every push. `main` deploys to
  production after a manual click in GitLab. Work on a feature branch and merge through a
  merge request. **Ask before pushing** to `development` or `main`.
- Commit messages: English, imperative mood, short ("Add dev accounts to try every role").
- **No AI attribution:** no `Co-Authored-By` lines and no mention of agents or assistants
  in commit messages or merge requests.
