# Operations

## Environments

Everything runs on VMs on the dorm's Proxmox servers.

| | Test / dev | Production |
| --- | --- | --- |
| Backend | `smartdormv2-api-dev.schollheim.net` | `api-smartdorm-v2.schollheim.net` (VM `api-smartdormv2`) |
| Frontend | `smartdormv2-dev.schollheim.net` | `smartdormv2.schollheim.net` (VM `web-smartdormv2`) |
| Database | `db-test-smartdorm-V2.schollheim.net` | VM `db-smartdorm` |
| LDAP | `ldap-test.schollheim.net` | `ldap.schollheim.net` |
| Deployed from | branch `development`, automatically | branch `main`, manual click |

The frontend's branch for the test system is called `develop`, the backend's `development`.

## Deploying

GitLab CI (`.gitlab-ci.yml`): `package_backend` bundles the repo (without `docs/`), then
`deploy_to_development` / `deploy_to_production` do the following:

1. `rsync --delete` to `/var/www/smartdorm/smartdormv2-backend/`, keeping the server's `.env`.
2. Write `.env` from the environment-scoped CI variable `ENV_FILE_CONTENT`.
3. Run `deploy.sh` on the server: create the venv, `pip install -r requirements.txt` +
   gunicorn, **`migrate`** (which also runs the startup checks, so a view without an access
   rule aborts the deploy here, before the restart), `collectstatic`, install the cron jobs,
   and `systemctl restart gunicorn`.

So: **a push to `development` is a deploy to the test server.** Production needs a merge to
`main` and the play button on the deploy job.

Env changes go into the GitLab CI variable `ENV_FILE_CONTENT` of the right environment,
not onto the server. The next deploy overwrites the server's `.env`.

## Scheduled jobs

Installed by `deploy.sh` into the deploy user's crontab, with output in `logs/cron.log`:

| When | Command |
| --- | --- |
| daily 04:00 | `manage.py recalculate_tenant_stats`: points, sublet months, extensions, LDAP groups ([ldap.md](ldap.md)) |
| Sundays 04:00 | `manage.py cleanup_old_logs --days 30` |

## Logs

- `logs/smartdorm.log`: the app log (INFO and up for Django, DEBUG for `smartdorm`). The
  Netzwerkreferat reads it in the frontend (`/api/engagements/logs/`).
- `logs/cron.log`: the nightly jobs.
- `sudo journalctl -u gunicorn --since "10 minutes ago"`: crashes and tracebacks.

Useful greps: `"Access denied by"` (access rule refusals), `"Blocked subtenant"`,
`"LDAP"` (group changes), `"Email sent"` / `"Failed to send email"`.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| 500 | The app crashed. Check the gunicorn journal. Often a missing `.env` value or the DB. |
| 502 | Gunicorn isn't running: `sudo systemctl status gunicorn`. |
| Deploy stops at `smartdorm.E001` | A view without exactly one access rule. The old version keeps running. Fix per [permissions.md](permissions.md). |
| 403 for one person | An access rule refused them. The log says which group was missing. If they were just given the group, they need to log in again. |
| 403 on every POST/PUT/DELETE | CSRF: the frontend origin is missing from `CSRF_TRUSTED_ORIGINS`, or the cookie domain is wrong (`LOCAL_ENV`). |
| Mails don't arrive on the test system | That's intended: they go to `DEVELOPER_EMAIL`. |
| Someone lost a group overnight | The nightly sync removed a managed group it couldn't justify. Grant it as a manual role (Netzwerkreferat page). |

## Runbooks

- [runbooks/server-setup.md](runbooks/server-setup.md): setting up a backend or frontend VM, and the GitLab CI variables and SSH key.
- [runbooks/demo.md](runbooks/demo.md): the Docker demo environment with fake data.
