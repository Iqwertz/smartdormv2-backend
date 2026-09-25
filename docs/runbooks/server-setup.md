# Runbook: setting up the servers

One-time setup of the backend and frontend VMs and of GitLab CI. The day-to-day picture
(environments, how a deploy runs, logs, troubleshooting) is in [../operations.md](../operations.md).
Some firewall and Nginx settings for HTTPS and for traffic between the admin and DMZ VLANs
aren't covered here.

## Prerequisites

-   Two VMs for the backend (dev/prod) and two VMs for the frontend (dev/prod).
-   Root or `sudo` access to all VMs.
-   DNS records pointing your domains/subdomains to the respective VM IP addresses.
-   A GitLab project with CI/CD enabled.


---

## Backend VM

This is a **one-time setup** required for the backend VM (both dev and prod).

### Step 1: Install System Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-dev libpq-dev python3-venv nginx curl redis-server rsync libsasl2-dev python-dev-is-python3 libldap2-dev libssl-dev libcups2-dev
```

### Step 2: Create Application User and Directory
The application will run under its own user for security.
The password for this user is the same on all VMS and saved in the vault under "SmartdormV2_Deployment -> DeploymentVMUserPw".
```bash
sudo adduser smartdorm
sudo mkdir -p /var/www/smartdorm/smartdormv2-backend
sudo usermod -aG smartdorm www-data
sudo chmod -R 750 /var/www/smartdorm/smartdormv2-backend/
sudo chmod -R g+rx /var/www/smartdorm/smartdormv2-backend/
sudo chown -R smartdorm:smartdorm /var/www/smartdorm
```

To allow the GitLab CI/CD pipeline to restart the gunicorn service without a password prompt, you need to edit the sudoers file.
```bash
sudo visudo
```
Here add the following line to the end of the file to allow the `smartdorm` user to restart the gunicorn service without a password. This is needed for the deployment script to work.
```plaintext
smartdorm ALL=(ALL) NOPASSWD: /bin/systemctl restart gunicorn 
```

### Step 3: Configure Gunicorn `systemd` Service
Create a service file that will create the gunicorn socket directory.

```bash
sudo nano /etc/tmpfiles.d/gunicorn.conf
```
Paste the following:
```plaintext
d /run/gunicorn 0770 smartdorm www-data -
```
Reload the `systemd` daemon to recognize the new tmpfiles configuration and create the directory:
```bash
sudo systemd-tmpfiles --create
sudo systemctl daemon-reload
```

Create a service file to manage the Gunicorn process.

`sudo nano /etc/systemd/system/gunicorn.service`

Paste the following configuration. This file tells `systemd` how to run, manage, and load environment variables for your Django app.

```ini
[Unit]
Description=gunicorn daemon for smartdorm
After=network.target

[Service]
User=smartdorm
Group=www-data
WorkingDirectory=/var/www/smartdorm/smartdormv2-backend

# load secrets from the .env file
EnvironmentFile=/var/www/smartdorm/smartdormv2-backend/.env

# The command to start Gunicorn, using a socket for communication with Nginx
ExecStart=/var/www/smartdorm/smartdormv2-backend/venv/bin/gunicorn \
          --access-logfile - \
          --workers 3 \
          --bind unix:/run/gunicorn/gunicorn.sock \
          smartdorm.wsgi:application

[Install]
WantedBy=multi-user.target
```

Enable and start the service (This will fail initially until the first deployment):
```bash
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
```

### Step 4: Configure Nginx as a Reverse Proxy
Create an Nginx configuration file for your backend site.

`sudo nano /etc/nginx/sites-available/smartdorm-backend`

Paste the following, replacing `smartdormv2-api-dev.schollheim.net` with the actual backend URL. (For public vms this has to be modified to use HTTPS using the schollheim.net wildcard certificates)

```nginx
server {
    listen 80;
    server_name smartdormv2-api-dev.schollheim.net;

    # Forward all application requests to the Gunicorn socket
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn/gunicorn.sock;
    }

    # Serve static files directly for performance
    location /static/ {
        root /var/www/smartdorm/smartdormv2-backend;
    }
}
```

Enable the site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/smartdorm-backend /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### Step 5: Configure Firewall
```bash
sudo apt -y install ufw
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## Frontend VM

This is a **one-time setup** required on each frontend VM.

### Step 1: Install Nginx
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y nginx rsync
```

### Step 2: Create Application User and Directory
The application will run under its own user for security. The password for this user is the same on all VMS and saved in the vault under "SmartdormV2_Deployment -> DeploymentVMUserPw".
```bash
sudo adduser smartdorm
sudo mkdir -p /var/www/smartdorm-frontend/html
sudo usermod -aG smartdorm www-data
sudo chmod -R 750 /var/www/smartdorm-frontend
sudo chmod -R g+rx /var/www/smartdorm-frontend
sudo chown -R smartdorm:smartdorm /var/www/smartdorm-frontend
```

### Step 3: Configure Nginx to Serve the React App
Create an Nginx configuration file for your frontend site.

`sudo nano /etc/nginx/sites-available/smartdorm-frontend`

Paste the following, replacing `dev.smartdorm.schollheim.net` with your actual frontend URL. 
Here also you would need to modify it to use HTTPS with the schollheim.net wildcard certificates for public vms.

```nginx
server {
    listen 80;
    server_name dev.smartdorm.schollheim.net;

    root /var/www/smartdorm-frontend/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Enable the site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/smartdorm-frontend /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```
### Step 4: Configure Firewall
```bash
sudo apt -y install ufw
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

---

## GitLab CI/CD

Automation is handled by GitLab. This setup uses environment-scoped variables and deploy keys for security.

### CI/CD variables
In each GitLab project (**frontend and backend**), go to **Settings > CI/CD > Variables**. Add the following variables, making sure to set the correct **Environment scope** (`development` or `production`) for each one.

#### Backend Variables:
-   `SERVER_IP`: IP of the target backend VM.
-   `SERVER_USER`: `smartdorm`
-   `SSH_PRIVATE_KEY`: Private SSH key for the GitLab runner to access the VM. (See below)
-   `ENV_FILE_CONTENT`: The full content of the `.env` file for the target environment.
    On `development` only, `export SHOW_DEV_ACCOUNTS=True` adds the test-account picker to the login page (see [Authentication & Permissions](../permissions.md#trying-it-out-dev-accounts)). Never set it for `production`.

#### Frontend Variables:
-   `SERVER_IP`: IP of the target frontend VM.
-   `SERVER_USER`: `smartdorm-fe`
-   `SSH_PRIVATE_KEY`: Private SSH key for the GitLab runner to access the VM. (See below)
-   `VITE_API_BASE_URL`: The full URL to the corresponding backend API (e.g., `http://smartdormv2-api-dev.schollheim.net/api`).

### SSH key for the GitLab runner

The `SSH_PRIVATE_KEY` variable is used by the GitLab runner to securely log into your server and perform deployment tasks. It is recommended to create a dedicated SSH keypair for this purpose.

1.  **Generate a new SSH keypair:**
    On your local machine (not on the server), run the following command. This will create a secure and modern `ed25519` key.

    ```bash
    ssh-keygen -t ed25519 -f ~/.ssh/gitlab_smartdorm_runner -C "GitLab Runner Key for SmartDorm"
    ```

    *   `-t ed25519`: Specifies the Ed25519 algorithm.
    *   `-f ~/.ssh/gitlab_smartdorm_runner`: Specifies the file path to save the key, preventing you from overwriting your personal `id_ed25519` key.
    *   `-C "..."`: Adds a helpful comment to the key.
    *   When prompted for a passphrase, press **Enter** to leave it empty. A passphrase would require manual input, which is not possible in an automated CI/CD pipeline.

2.  **Get the private key:**
    The command will generate two files: `gitlab_smartdorm_runner` (the private key) and `gitlab_smartdorm_runner.pub` (the public key).
    Display the **private key** in your terminal:

    ```bash
    cat ~/.ssh/gitlab_smartdorm_runner
    ```
    Copy the entire output, including the `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----` lines. This is the value you will paste into the `SSH_PRIVATE_KEY` variable in GitLab.

3.  **Get the public key:**
    Display the **public key** in your terminal:

    ```bash
    cat ~/.ssh/gitlab_smartdorm_runner.pub
    ```
    Copy this entire line.

4.  **Add the public key to the VM:**
    SSH into the VM (e.g., as the `smartdorm` user). Append the public key you just copied to the `~/.ssh/authorized_keys` file.

    ```bash
    echo "paste-your-public-key-here" >> ~/.ssh/authorized_keys
    ```
    This action grants the GitLab runner—which now holds the corresponding private key—permission to log into that user account on the server.

### The pipelines
The CI configuration is defined in the `.gitlab-ci.yml` file in the root of each repository.
-   **Backend Pipeline:** Copies the `ENV_FILE_CONTENT` to the server as `.env` and then executes the `deploy.sh` script on the server, which pulls the latest code, runs migrations, and restarts the Gunicorn service.
-   **Frontend Pipeline:** First builds the React application, injecting the correct `VITE_API_BASE_URL`. It then uses `rsync` to copy the built static files (`dist/` folder) directly to the Nginx web root on the server.
