# Deploying the Demo Environment

This guide explains how to deploy the demo environment of SmartDorm onto a VPS using Docker Compose and Nginx as a reverse proxy.

## Prerequisites
- A VPS running Linux (Ubuntu/Debian recommended)
- `docker` and `docker compose` installed
- `nginx` installed (`sudo apt install nginx`)
- A domain name (e.g., `smartdorm.juliushussl.at`) pointed to your VPS's IP address.

## 1. Setup the project on the VPS

1. SSH into your VPS.
2. Clone the repository and checkout your demo branch.
   ```bash
   git clone <your-repo-url> smartdorm-demo
   cd smartdorm-demo
   git checkout demo-mode # (or whichever branch holds the demo files)
   ```

## 2. Fix Docker metadata error (If applicable)
If you encounter the error `open /tmp/.tmp-compose-build-metadataFile...: no such file or directory` when running `docker compose up --build`:
This is a known bug in certain versions of the `docker-compose` CLI plugin related to BuildKit metadata generation.

**Solution:** Disable provenance when building.
Run the build command prefixing it with an environment variable:
```bash
BUILDX_NO_DEFAULT_ATTESTATIONS=1 docker compose -f docker-compose.demo.yml up -d --build
```

## 3. Run the Demo Stack

Start the demo stack. By default, it maps the Django backend entirely to **port 8005** on your host to avoid clashing with other services on `8000`.

```bash
DOCKER_BUILDKIT=0 docker compose -f docker-compose.demo.yml up -d --build
```
> **Note**: It may take a minute or two for the `demo-entrypoint.sh` to initialize the database and generate the 600 fake users before the web server responds.

## 4. Nginx Reverse Proxy Setup

Create a new Nginx configuration file for your domain.

```bash
sudo nano /etc/nginx/sites-available/smartdorm_demo
```

Add the following configuration. This proxies requests from `smartdorm-api.juliushussl.at` to your docker container running on port `8005`:

```nginx
server {
    listen 80;
    server_name smartdorm-api.juliushussl.at;

    location / {
        proxy_pass http://127.0.0.1:8005;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Ensure CORS credentials and tokens are handled smoothly
        proxy_set_header Cookie $http_cookie;
    }
}
```

Enable the site and reload Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/smartdorm_demo /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 5. Secure with SSL (Certbot)

It's highly recommended to secure your demo with HTTPS.
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d smartdorm.juliushussl.at
```

## 6. Accessing the Demo
You can now navigate to `https://smartdorm.juliushussl.at`.
Login with the seeded LDAP admin account:
- **Username**: `demo`
- **Password**: `demo`
