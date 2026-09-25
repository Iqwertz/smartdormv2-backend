# Runbook: the demo environment

A self-contained Docker setup that shows SmartDorm to outsiders without real data or
secrets. It isn't meant for testing. The files are `docker-compose.demo.yml`,
`Dockerfile.demo`, `.env.demo`, `scripts/demo-entrypoint.sh` and `scripts/demo-ldap/`.
The branch `demo-mode` holds the demo-specific changes.

## What it does

- Starts Postgres, Redis, a small OpenLDAP (`scripts/demo-ldap/`) and the backend under Gunicorn.
- At build time, the legacy models are patched to `managed = True`. The entrypoint then runs
  `makemigrations` + `migrate` against the empty demo DB, so Django creates every table.
  **This happens only inside the demo container.** Never do it against a real database.
- `manage.py generate_demo_data` fills in about 600 fake tenants, rooms, Referate,
  subtenants, engagements, claims and bank data.

## Running it

```bash
docker compose -f docker-compose.demo.yml up -d --build      # API on http://localhost:8005
docker compose -f docker-compose.demo.yml down -v             # stop and wipe the demo DB
```

The first start takes a minute or two while the migrations and fake data are generated.

Logins (both in `ADMIN`): `demo` / `demo` and `admin` / `admin`. The frontend shows a hint
for the demo login when built with `VITE_DEMO_MODE=true`.

If the build fails with `open /tmp/.tmp-compose-build-metadataFile…`, a docker-compose
BuildKit bug, build with `BUILDX_NO_DEFAULT_ATTESTATIONS=1` or `DOCKER_BUILDKIT=0`.

## Hosting it on a VPS

1. Clone the repo, check out `demo-mode`, and start the stack as above.
2. Nginx reverse proxy to `127.0.0.1:8005`:

   ```nginx
   server {
       listen 80;
       server_name smartdorm-api.example.org;
       location / {
           proxy_pass http://127.0.0.1:8005;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_set_header Cookie $http_cookie;
       }
   }
   ```

3. HTTPS with `certbot --nginx -d <domain>`.
