# Development

## Setup

```bash
pyenv install                         # Python version from .python-version (3.13)
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .sample.env .env                   # fill the secrets from the vault
sudo apt install redis-server && sudo service redis-server start
```

`python-ldap` and `pycups` need system headers (`libldap2-dev libsasl2-dev libcups2-dev`).
There is no system `python` in the usual WSL setup, so call `.venv/bin/python` or activate the
venv first. `run-server.sh` and `run-tests.sh` call plain `python`.

## The `.env` and which database you're on

`.env` lines are written as `export KEY=value`. Load it with:

```bash
set -a; source .env; set +a
echo $DB_HOST       # check before any manage.py command that writes
```

- Sourcing prints a harmless `^623: command not found`, because `SECRET_KEY` contains `&&^`.
- **Without `.env`, `manage.py` silently uses a local Postgres** (`settings.py` falls back to
  `localhost` / `testing`). The dev database has the same name and also holds real-looking
  data, so nothing looks wrong. A `migrate` just lands in the wrong database.
- The dev database is remote (`db-test-smartdorm-V2.schollheim.net`) and holds **real data**.
  Most models are `managed = False`, and the Django test runner can't build those tables. So
  checks that need data run against the dev DB. Wrap writes and roll back:

  ```python
  from django.db import transaction
  with transaction.atomic():
      ...                      # try things
      raise RuntimeError("rollback")
  ```

- For quick scripts: `PYTHONPATH=. .venv/bin/python script.py` with
  `DJANGO_SETTINGS_MODULE=smartdorm.settings`. For the Django test client add
  `ALLOWED_HOSTS=testserver`.

Important env vars (full list in `.sample.env`):

| Var | Meaning |
| --- | --- |
| `PRODUCTION` | `True` only on the production server. Turns off `DEBUG` and mail redirection. |
| `DEVELOPER_EMAIL` | Outside production, **every** mail goes here instead of to the real recipient. Unset = no mail at all. |
| `LOCAL_ENV` | `True` on localhost: cookies aren't scoped to `.schollheim.net`. |
| `LDAP_URI`, `LDAP_ADMIN_PASSWORD` | Use `ldap-test.schollheim.net` in development. |
| `SHOW_DEV_ACCOUNTS` | Test systems only: the login page offers the dev accounts. |
| `REDIS_URL`, `DB_*`, `POSTGRES_*`, `SECRET_KEY`, `EMAIL_HOST_PASSWORD` | the obvious |
| `DEVICE_AGENT_TOKEN` | shared secret of the Pi print agent |

## Running

```bash
source .venv/bin/activate
./run-server.sh        # checks Redis and the DB, migrates, runserver 0.0.0.0:8000
```

The frontend dev server (`localhost:5173`) is already allowed by CORS and CSRF.
`run-server.sh` also runs `makemigrations`. Check `git status` for stray migration files
before committing (tracked in [todo.md](todo.md)).

## Tests

```bash
.venv/bin/python manage.py test smartdorm.tests.test_access smartdorm.tests.test_dev_accounts
```

These run in under a second without a database. They cover every access rule and the reviewed
access snapshot. `./run-tests.sh` runs them first and then the integration tests, which need a
test database and are currently broken (see [todo.md](todo.md)).

After changing access: `manage.py list_api_access --write-snapshot` and commit
`smartdorm/tests/api_access.txt`. See [permissions.md](permissions.md).

## Trying things as a role

The test LDAP has one account per role (`dev-bewohner`, `dev-verwaltung`, `dev-heimrat`, …).
`manage.py dev_accounts` creates or resets them (it refuses to run against anything but the
test LDAP and test DB), and `SHOW_DEV_ACCOUNTS=True` puts them on the login page. Details in
[permissions.md](permissions.md#trying-it-out-dev-accounts).

## Useful commands

| Command | What it does |
| --- | --- |
| `manage.py check` | runs the startup checks, including the access rule check `smartdorm.E001` |
| `manage.py list_api_access [--rule IsVerwaltung]` | who may call which endpoint |
| `manage.py recalculate_tenant_stats --dry-run` | the nightly job, printing what it would change without saving stats or writing LDAP |
| `manage.py verify_contract_dates [--tenant j.doe]` | compare stored and calculated move-out dates, interactively |
| `manage.py verify_schema` | compare the models with the real DB schema |
| `manage.py cleanup_old_logs --days 30` | trim `logs/smartdorm.log` |
| `manage.py dev_accounts [--delete]` | the per-role test accounts |
| `manage.py generate_demo_data` | fake data for the demo environment only |
| `scripts/setup_device_print.py` | create or reset the print device |

LDAP inspection commands are in [ldap.md](ldap.md#useful-commands).
