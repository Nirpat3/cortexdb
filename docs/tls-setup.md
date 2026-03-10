# CortexDB TLS/HTTPS Setup Guide

This document covers TLS certificate configuration for CortexDB, from local
development through production deployment.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Development Setup (Self-Signed)](#development-setup-self-signed)
3. [Production Setup (Let's Encrypt)](#production-setup-lets-encrypt)
4. [Custom CA Certificates](#custom-ca-certificates)
5. [Certificate Renewal Automation](#certificate-renewal-automation)
6. [Troubleshooting](#troubleshooting)
7. [Testing TLS Configuration](#testing-tls-configuration)

---

## Architecture Overview

CortexDB uses Nginx as a reverse proxy for TLS termination. All external
traffic enters through Nginx on ports 80 (HTTP, redirects to HTTPS) and
443 (HTTPS). Internal service-to-service communication remains unencrypted
over the Docker bridge network.

```
Internet
   |
   v
[Nginx :443] --TLS termination-->  [cortex-router :5400]  (API)
   |                                [cortex-dashboard :3000] (UI)
   |
   +-- /api/    --> cortex-router
   +-- /v1/     --> cortex-router
   +-- /health/ --> cortex-router
   +-- /ws/     --> cortex-router (WebSocket upgrade)
   +-- /        --> cortex-dashboard
```

**Files involved:**

| File | Purpose |
|------|---------|
| `nginx/nginx.conf` | Nginx configuration with TLS, rate limiting, headers |
| `nginx/Dockerfile` | Nginx container definition |
| `certs/` | Certificate directory (gitignored) |
| `docker-compose.prod.yml` | Production override with Nginx service |
| `scripts/generate-certs.sh` | Certificate generation utility |

---

## Development Setup (Self-Signed)

Self-signed certificates allow HTTPS locally without a domain name or
public IP.

### Step 1: Generate certificates

```bash
chmod +x scripts/generate-certs.sh
./scripts/generate-certs.sh --dev
```

This creates the `certs/` directory with:

- `ca.key` / `ca.crt` -- Local CA key pair
- `cortexdb.key` / `cortexdb.crt` -- Server certificate
- `dhparam.pem` -- Diffie-Hellman parameters
- `chain.pem` -- Full certificate chain

The certificate includes SANs for `localhost`, `127.0.0.1`, `::1`,
`cortex-router`, and `cortex-dashboard`.

### Step 2: Trust the CA (optional, removes browser warnings)

**macOS:**
```bash
sudo security add-trusted-cert -d -r trustRoot \
    -k /Library/Keychains/System.keychain certs/ca.crt
```

**Ubuntu/Debian:**
```bash
sudo cp certs/ca.crt /usr/local/share/ca-certificates/cortexdb-ca.crt
sudo update-ca-certificates
```

**Windows:**
```powershell
certutil -addstore -f "ROOT" certs\ca.crt
```

### Step 3: Start with TLS

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

CortexDB is now available at `https://localhost`.

### Custom domain for development

```bash
./scripts/generate-certs.sh --dev --domain mydb.local
```

Add an entry to `/etc/hosts` (or `C:\Windows\System32\drivers\etc\hosts`):
```
127.0.0.1  mydb.local
```

---

## Production Setup (Let's Encrypt)

Let's Encrypt provides free, automatically-renewed TLS certificates
trusted by all major browsers.

### Prerequisites

- A registered domain name pointing to your server (A/AAAA records)
- Ports 80 and 443 open in your firewall
- `certbot` installed on the host

### Option A: Standalone mode (before first start)

```bash
sudo certbot certonly --standalone \
    -d your-domain.com \
    --email admin@your-domain.com \
    --agree-tos \
    --no-eff-email
```

Copy the certificates:
```bash
mkdir -p certs
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem certs/cortexdb.crt
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem certs/cortexdb.key
openssl dhparam -out certs/dhparam.pem 2048
```

Set ownership:
```bash
chmod 600 certs/cortexdb.key
chmod 644 certs/cortexdb.crt certs/dhparam.pem
```

### Option B: Webroot mode (while running)

The Nginx configuration serves ACME challenges from `/var/www/certbot`.

```bash
sudo certbot certonly --webroot \
    -w /path/to/cortexdb/certbot-webroot \
    -d your-domain.com \
    --email admin@your-domain.com \
    --agree-tos
```

Then copy certificates as shown in Option A and restart Nginx:
```bash
docker compose restart nginx
```

### Option C: DNS challenge (wildcard certificates)

For wildcard certs (`*.your-domain.com`):

```bash
sudo certbot certonly --manual \
    --preferred-challenges dns \
    -d "*.your-domain.com" \
    -d your-domain.com \
    --email admin@your-domain.com \
    --agree-tos
```

Follow the prompts to add DNS TXT records, then copy certificates
as shown in Option A.

### Start with production TLS

```bash
# Set required environment variables
cp .env.example .env
# Edit .env with production passwords

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Custom CA Certificates

For organizations using an internal CA (corporate PKI):

### Step 1: Prepare certificate files

Place the following in `certs/`:

- `cortexdb.crt` -- Server certificate (PEM format)
- `cortexdb.key` -- Server private key (PEM format)
- `chain.pem` -- Full chain including intermediates (optional, for OCSP stapling)
- `dhparam.pem` -- Generate with `openssl dhparam -out certs/dhparam.pem 2048`

### Step 2: Enable OCSP stapling (if your CA supports it)

Edit `nginx/nginx.conf` and uncomment the OCSP stapling section:

```nginx
ssl_stapling on;
ssl_stapling_verify on;
ssl_trusted_certificate /etc/nginx/ssl/chain.pem;
```

### Step 3: Convert formats if needed

**From PKCS#12 (.pfx/.p12):**
```bash
openssl pkcs12 -in cert.pfx -nocerts -nodes -out certs/cortexdb.key
openssl pkcs12 -in cert.pfx -clcerts -nokeys -out certs/cortexdb.crt
```

**From DER to PEM:**
```bash
openssl x509 -inform DER -in cert.der -out certs/cortexdb.crt
openssl rsa -inform DER -in key.der -out certs/cortexdb.key
```

---

## Certificate Renewal Automation

### Let's Encrypt auto-renewal with cron

```bash
# Edit root crontab
sudo crontab -e

# Add (runs daily at 3 AM, restarts nginx on renewal):
0 3 * * * certbot renew --quiet \
    --deploy-hook "cp /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem /path/to/cortexdb/certs/cortexdb.crt && \
                   cp /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem /path/to/cortexdb/certs/cortexdb.key && \
                   docker compose -f /path/to/cortexdb/docker-compose.yml -f /path/to/cortexdb/docker-compose.prod.yml restart nginx"
```

### Let's Encrypt auto-renewal with systemd

```ini
# /etc/systemd/system/cortexdb-cert-renew.service
[Unit]
Description=Renew CortexDB TLS certificates

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet
ExecStartPost=/bin/bash -c 'cp /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem /path/to/cortexdb/certs/cortexdb.crt'
ExecStartPost=/bin/bash -c 'cp /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem /path/to/cortexdb/certs/cortexdb.key'
ExecStartPost=/usr/bin/docker compose -f /path/to/cortexdb/docker-compose.yml -f /path/to/cortexdb/docker-compose.prod.yml restart nginx
```

```ini
# /etc/systemd/system/cortexdb-cert-renew.timer
[Unit]
Description=Renew CortexDB TLS certificates daily

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with:
```bash
sudo systemctl enable --now cortexdb-cert-renew.timer
```

### Self-signed certificate renewal

Self-signed certs do not auto-renew. Regenerate before expiry:

```bash
./scripts/generate-certs.sh --dev --days 730
docker compose restart nginx
```

Check current certificate expiry:
```bash
openssl x509 -in certs/cortexdb.crt -noout -enddate
```

---

## Troubleshooting

### "SSL: error" or connection refused on port 443

1. Verify certificates exist:
   ```bash
   ls -la certs/
   ```
   Expected files: `cortexdb.crt`, `cortexdb.key`, `dhparam.pem`

2. Check certificate validity:
   ```bash
   openssl x509 -in certs/cortexdb.crt -noout -dates
   ```

3. Check Nginx logs:
   ```bash
   docker compose logs nginx
   ```

4. Verify the key matches the certificate:
   ```bash
   openssl x509 -noout -modulus -in certs/cortexdb.crt | openssl md5
   openssl rsa -noout -modulus -in certs/cortexdb.key | openssl md5
   ```
   Both MD5 hashes must match.

### Browser shows "Not Secure" with self-signed certs

This is expected. Either trust the CA certificate (see Development Setup,
Step 2) or use Let's Encrypt for production.

### "certificate verify failed" from internal services

Internal services communicate over HTTP on the Docker network. If a service
is configured to connect via HTTPS to the public URL, either:

- Change the service URL to use the internal Docker hostname and HTTP port
- Add the CA certificate to the service's trust store

### Mixed content warnings

Ensure `CORTEX_CORS_ORIGINS` in `.env` uses `https://` URLs:
```
CORTEX_CORS_ORIGINS=https://your-domain.com
```

### Certificate chain issues

Verify the full chain:
```bash
openssl verify -CAfile certs/ca.crt certs/cortexdb.crt
```

For Let's Encrypt, ensure you are using `fullchain.pem` (not `cert.pem`)
as the certificate file.

### DH parameter errors

Regenerate DH parameters:
```bash
openssl dhparam -out certs/dhparam.pem 2048
```

### Permission denied on certificate files

```bash
chmod 600 certs/cortexdb.key
chmod 644 certs/cortexdb.crt certs/dhparam.pem
```

The key file must be readable by the Nginx process (runs as root in the
container, reads certs before dropping privileges).

---

## Testing TLS Configuration

### Quick local test

```bash
# Check TLS handshake
openssl s_client -connect localhost:443 -servername localhost </dev/null 2>/dev/null

# Show certificate details
openssl s_client -connect localhost:443 </dev/null 2>/dev/null | openssl x509 -noout -text

# Check supported protocols
openssl s_client -connect localhost:443 -tls1_2 </dev/null 2>/dev/null && echo "TLS 1.2: OK"
openssl s_client -connect localhost:443 -tls1_3 </dev/null 2>/dev/null && echo "TLS 1.3: OK"

# Verify TLS 1.0/1.1 are rejected
openssl s_client -connect localhost:443 -tls1 </dev/null 2>/dev/null || echo "TLS 1.0: Correctly rejected"
openssl s_client -connect localhost:443 -tls1_1 </dev/null 2>/dev/null || echo "TLS 1.1: Correctly rejected"
```

### curl verification

```bash
# With self-signed CA
curl --cacert certs/ca.crt https://localhost/health/ready

# Skip verification (development only)
curl -k https://localhost/health/ready
```

### SSL Labs (production only)

For publicly accessible deployments, test at:
  https://www.ssllabs.com/ssltest/

Target grade: A or A+. The provided configuration with TLS 1.2+, strong
ciphers, HSTS, and DH parameters should achieve an A rating.

### testssl.sh (comprehensive local testing)

```bash
# Install testssl.sh
git clone --depth 1 https://github.com/drwetter/testssl.sh.git

# Run full test
./testssl.sh/testssl.sh https://localhost:443

# Specific checks
./testssl.sh/testssl.sh --protocols https://localhost:443
./testssl.sh/testssl.sh --headers https://localhost:443
./testssl.sh/testssl.sh --vulnerable https://localhost:443
```

### nmap SSL audit

```bash
nmap --script ssl-enum-ciphers -p 443 localhost
```

### Security header verification

```bash
curl -sI https://localhost/ 2>/dev/null | grep -iE '(strict|x-frame|x-content|referrer|content-security|permissions)'
```

Expected output should include all six security headers:
- `Strict-Transport-Security`
- `X-Frame-Options`
- `X-Content-Type-Options`
- `X-XSS-Protection`
- `Referrer-Policy`
- `Content-Security-Policy`
