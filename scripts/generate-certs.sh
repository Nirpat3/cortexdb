#!/usr/bin/env bash
# ============================================================
# CortexDB - TLS Certificate Generator
# Generates self-signed certs (dev) or provides Let's Encrypt
# instructions (prod).
# (c) 2026 Nirlab Inc. All Rights Reserved.
# ============================================================
#
# Usage:
#   ./scripts/generate-certs.sh --dev              # Self-signed for development
#   ./scripts/generate-certs.sh --dev --domain foo  # Self-signed with custom CN
#   ./scripts/generate-certs.sh --prod              # Let's Encrypt instructions
#
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CERTS_DIR="$PROJECT_DIR/certs"
DOMAIN="${DOMAIN:-cortexdb.local}"
CERT_DAYS=365
KEY_SIZE=4096
DH_SIZE=2048

# Colors for output (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' NC=''
fi

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
    cat <<'USAGE'
CortexDB TLS Certificate Generator

Usage:
  generate-certs.sh --dev [OPTIONS]     Generate self-signed certificates
  generate-certs.sh --prod [OPTIONS]    Show Let's Encrypt setup instructions

Options:
  --domain DOMAIN   Domain name for certificate (default: cortexdb.local)
  --days DAYS       Certificate validity in days (default: 365)
  --key-size SIZE   RSA key size in bits (default: 4096)
  --dh-size SIZE    DH parameter size in bits (default: 2048)
  --output DIR      Output directory (default: ./certs)
  -h, --help        Show this help message

Examples:
  generate-certs.sh --dev
  generate-certs.sh --dev --domain mydb.example.com --days 730
  generate-certs.sh --prod --domain mydb.example.com
USAGE
    exit 0
}

# -----------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------
MODE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)       MODE="dev";  shift ;;
        --prod)      MODE="prod"; shift ;;
        --domain)    DOMAIN="$2"; shift 2 ;;
        --days)      CERT_DAYS="$2"; shift 2 ;;
        --key-size)  KEY_SIZE="$2"; shift 2 ;;
        --dh-size)   DH_SIZE="$2"; shift 2 ;;
        --output)    CERTS_DIR="$2"; shift 2 ;;
        -h|--help)   usage ;;
        *)           log_error "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$MODE" ]]; then
    log_error "Must specify --dev or --prod"
    usage
fi

# -----------------------------------------------------------
# Check prerequisites
# -----------------------------------------------------------
check_openssl() {
    if ! command -v openssl &>/dev/null; then
        log_error "openssl is required but not found. Install it first."
        exit 1
    fi
    log_info "Using openssl: $(openssl version)"
}

# -----------------------------------------------------------
# Generate self-signed certificates (development)
# -----------------------------------------------------------
generate_dev_certs() {
    check_openssl

    log_info "Generating self-signed certificates for development"
    log_info "Domain: $DOMAIN"
    log_info "Output: $CERTS_DIR"

    # Create output directory with restrictive permissions
    mkdir -p "$CERTS_DIR"
    chmod 700 "$CERTS_DIR"

    # Check for existing certificates
    if [[ -f "$CERTS_DIR/cortexdb.crt" ]]; then
        log_warn "Existing certificates found in $CERTS_DIR"
        read -rp "Overwrite? [y/N] " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Aborted. Existing certificates preserved."
            exit 0
        fi
    fi

    # Generate CA key and certificate
    log_info "Generating CA private key..."
    openssl genrsa -out "$CERTS_DIR/ca.key" "$KEY_SIZE" 2>/dev/null

    log_info "Generating CA certificate..."
    openssl req -new -x509 \
        -key "$CERTS_DIR/ca.key" \
        -out "$CERTS_DIR/ca.crt" \
        -days "$CERT_DAYS" \
        -subj "/C=US/ST=California/L=SanFrancisco/O=CortexDB Dev/OU=Engineering/CN=CortexDB Dev CA"

    # Generate server key
    log_info "Generating server private key..."
    openssl genrsa -out "$CERTS_DIR/cortexdb.key" "$KEY_SIZE" 2>/dev/null

    # Generate CSR with SANs
    log_info "Generating certificate signing request..."
    cat > "$CERTS_DIR/openssl-san.cnf" <<EOF
[req]
default_bits = $KEY_SIZE
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C = US
ST = California
L = San Francisco
O = CortexDB Dev
OU = Engineering
CN = $DOMAIN

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = $DOMAIN
DNS.2 = localhost
DNS.3 = cortex-router
DNS.4 = cortex-dashboard
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

    openssl req -new \
        -key "$CERTS_DIR/cortexdb.key" \
        -out "$CERTS_DIR/cortexdb.csr" \
        -config "$CERTS_DIR/openssl-san.cnf"

    # Sign the certificate with our CA
    log_info "Signing server certificate with CA..."
    openssl x509 -req \
        -in "$CERTS_DIR/cortexdb.csr" \
        -CA "$CERTS_DIR/ca.crt" \
        -CAkey "$CERTS_DIR/ca.key" \
        -CAcreateserial \
        -out "$CERTS_DIR/cortexdb.crt" \
        -days "$CERT_DAYS" \
        -sha256 \
        -extensions v3_req \
        -extfile "$CERTS_DIR/openssl-san.cnf"

    # Generate DH parameters
    log_info "Generating DH parameters ($DH_SIZE bit) -- this may take a moment..."
    openssl dhparam -out "$CERTS_DIR/dhparam.pem" "$DH_SIZE" 2>/dev/null

    # Create combined chain file
    cat "$CERTS_DIR/cortexdb.crt" "$CERTS_DIR/ca.crt" > "$CERTS_DIR/chain.pem"

    # Set permissions
    chmod 600 "$CERTS_DIR"/*.key
    chmod 644 "$CERTS_DIR"/*.crt "$CERTS_DIR"/*.pem
    chmod 644 "$CERTS_DIR"/openssl-san.cnf

    # Clean up CSR and serial (not needed after signing)
    rm -f "$CERTS_DIR/cortexdb.csr" "$CERTS_DIR/ca.srl"

    log_info "Certificate generation complete."
    echo ""
    echo "Files created:"
    echo "  $CERTS_DIR/ca.key          - CA private key (keep secure)"
    echo "  $CERTS_DIR/ca.crt          - CA certificate (install in browser/OS)"
    echo "  $CERTS_DIR/cortexdb.key    - Server private key"
    echo "  $CERTS_DIR/cortexdb.crt    - Server certificate"
    echo "  $CERTS_DIR/dhparam.pem     - DH parameters"
    echo "  $CERTS_DIR/chain.pem       - Full certificate chain"
    echo ""
    echo "To trust the CA on your system:"
    echo "  macOS:   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain $CERTS_DIR/ca.crt"
    echo "  Ubuntu:  sudo cp $CERTS_DIR/ca.crt /usr/local/share/ca-certificates/cortexdb-ca.crt && sudo update-ca-certificates"
    echo "  Windows: certutil -addstore -f \"ROOT\" $CERTS_DIR\\ca.crt"
    echo ""
    log_info "Start CortexDB with TLS: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
}

# -----------------------------------------------------------
# Production Let's Encrypt instructions
# -----------------------------------------------------------
show_prod_instructions() {
    cat <<'PROD'
=============================================================
CortexDB - Production TLS Setup with Let's Encrypt
=============================================================

PREREQUISITES:
  - A registered domain pointing to your server's public IP
  - Ports 80 and 443 open in your firewall
  - certbot installed (https://certbot.eff.org)

OPTION 1: Standalone (before starting CortexDB)
-----------------------------------------------
  sudo certbot certonly --standalone \
      -d YOUR_DOMAIN \
      --email YOUR_EMAIL \
      --agree-tos \
      --no-eff-email

  Then copy certificates:
    mkdir -p ./certs
    sudo cp /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem ./certs/cortexdb.crt
    sudo cp /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem ./certs/cortexdb.key
    openssl dhparam -out ./certs/dhparam.pem 2048

OPTION 2: Webroot (while CortexDB is running)
----------------------------------------------
  Nginx is configured to serve /.well-known/acme-challenge/ from /var/www/certbot.

  1. Start CortexDB with HTTP only first (temporarily comment SSL in nginx.conf)
  2. Run certbot:
     sudo certbot certonly --webroot \
         -w /var/www/certbot \
         -d YOUR_DOMAIN \
         --email YOUR_EMAIL \
         --agree-tos

  3. Copy certs as shown in Option 1
  4. Restart nginx: docker compose restart nginx

OPTION 3: DNS challenge (wildcard certs)
-----------------------------------------
  sudo certbot certonly --manual \
      --preferred-challenges dns \
      -d "*.YOUR_DOMAIN" \
      -d YOUR_DOMAIN \
      --email YOUR_EMAIL \
      --agree-tos

AUTO-RENEWAL:
  Add to crontab (sudo crontab -e):
    0 3 * * * certbot renew --quiet --deploy-hook "docker compose -C /path/to/cortexdb restart nginx"

  Or create a systemd timer for more reliable scheduling.

VERIFY CERTIFICATES:
  openssl s_client -connect YOUR_DOMAIN:443 -servername YOUR_DOMAIN < /dev/null 2>/dev/null | openssl x509 -noout -dates
=============================================================
PROD

    log_info "Replace YOUR_DOMAIN and YOUR_EMAIL with your actual values."
}

# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
case "$MODE" in
    dev)  generate_dev_certs ;;
    prod) show_prod_instructions ;;
esac
