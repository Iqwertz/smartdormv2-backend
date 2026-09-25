# SmartDorm backend knowledge base

Read this before working on the backend. It collects what we know about the dorm, the code
and how it runs, so you don't have to rediscover it. Everything here was checked against the
code in September 2026. Where the code and a doc disagree, trust the code and fix the doc.

| File | Read it when you need… |
| --- | --- |
| [domain/selbstverwaltung.md](domain/selbstverwaltung.md) | how the dorm is run, the semester cycle, points, and who uses which part of SmartDorm |
| [domain/glossary.md](domain/glossary.md) | the German terms and their names in the code |
| [domain/tenant-lifecycle.md](domain/tenant-lifecycle.md) | move-in, room moves, move-out, signatures, extension requests, terminations |
| [domain/contract-dates.md](domain/contract-dates.md) | how `move_out` and `probation_end` are calculated, and how to change them properly |
| [domain/engagements.md](domain/engagements.md) | Referate: applications, engagements, points and Entlastung, the semester switch |
| [domain/subtenants.md](domain/subtenants.md) | subtenants, their accounts and what they may access |
| [architecture.md](architecture.md) | code layout, conventions, the database (legacy vs. Django tables, **how to add columns**), LDAP + DB ordering |
| [permissions.md](permissions.md) | login, access rules, adding or changing an endpoint, dev accounts, 403 troubleshooting |
| [ldap.md](ldap.md) | accounts, groups, the nightly sync, manual roles |
| [features/printing.md](features/printing.md) | printing and scanning, the Pi agent, billing |
| [features/attendance.md](features/attendance.md) | QR attendance at assemblies |
| [features/parcels.md](features/parcels.md) | the parcel desk |
| [development.md](development.md) | local setup, the `.env` traps, tests, useful commands |
| [operations.md](operations.md) | environments, deploys, cron jobs, logs, troubleshooting |
| [runbooks/](runbooks/) | server setup and the demo environment, step by step |
| [decisions.md](decisions.md) | why things are the way they are |
| [todo.md](todo.md) | open bugs, cleanups, projects and ideas |
| [open-questions.md](open-questions.md) | things we don't know yet |

The frontend has its own knowledge base in `../smartdormv2-frontend/docs/`, including the voice
and design guides. Domain knowledge lives here and the frontend links to it.

## Keeping this current

- Change the docs in the same commit as the code they describe.
- New topic? Create a file and add a row to the table above. A doc nobody can find doesn't help.
- Write for someone who knows Django but not the dorm. Short, concrete, with file and function
  names. Say *why* when it isn't obvious.
- Tick answered questions in `open-questions.md` and move the answer to where it belongs.
- Don't copy secrets (passwords, tokens, `.env` values) into docs. Hostnames are fine; the
  repo is private.
