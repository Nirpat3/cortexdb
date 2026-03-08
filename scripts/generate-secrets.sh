#!/usr/bin/env bash
# ============================================================
# CortexDB — Generate Production Secrets
# Creates a .env file with cryptographically random secrets
#
# Usage:
#   ./scripts/generate-secrets.sh                    # Generate .env
#   ./scripts/generate-secrets.sh --domain mydb.com  # Set domain
#   ./scripts/generate-secrets.sh --output .env.prod  # Custom output
# ============================================================

set -euo pipefail

DOMAIN="cortexdb.example.com"
OUTPUT=".env"

for i in "$@"; do
  case $i in
    --domain=*)  DOMAIN="${i#*=}" ;;
    --domain)    shift; DOMAIN="${2:-$DOMAIN}" ;;
    --output=*)  OUTPUT="${i#*=}" ;;
    --output)    shift; OUTPUT="${2:-$OUTPUT}" ;;
    --help)
      echo "Usage: $0 [--domain=example.com] [--output=.env]"
      exit 0
      ;;
  esac
done

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_PATH="$PROJECT_DIR/$OUTPUT"

# Generate random hex string
rand_hex() { openssl rand -hex "$1" 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex($1))"; }

# Generate random alphanumeric
rand_alnum() { openssl rand -base64 "$1" 2>/dev/null | tr -dc 'a-zA-Z0-9' | head -c "$1" || python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range($1)))"; }

if [ -f "$OUTPUT_PATH" ]; then
  echo "WARNING: $OUTPUT already exists."
  read -rp "Overwrite? [y/N] " confirm
  if [[ "$confirm" != [yY] ]]; then
    echo "Aborted."
    exit 0
  fi
  cp "$OUTPUT_PATH" "${OUTPUT_PATH}.backup.$(date +%s)"
fi

SECRET_KEY=$(rand_hex 32)
ADMIN_TOKEN=$(rand_hex 24)
MASTER_KEY=$(rand_hex 32)
MASTER_SECRET=$(rand_alnum 32)
PG_PASS=$(rand_alnum 24)
REDIS_PASS=$(rand_alnum 24)
STREAM_PASS=$(rand_alnum 24)
GRAFANA_PASS=$(rand_alnum 16)
METRICS_TOKEN=$(rand_hex 16)

cat > "$OUTPUT_PATH" << EOF
# ============================================================
# CortexDB — Production Environment
# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# Domain: $DOMAIN
#
# KEEP THIS FILE SECURE — contains production secrets
# ============================================================

# Domain
CORTEX_DOMAIN=$DOMAIN

# Environment
CORTEX_ENV=production

# Security keys (auto-generated, 64+ chars)
CORTEX_SECRET_KEY=$SECRET_KEY
CORTEX_ADMIN_TOKEN=$ADMIN_TOKEN
CORTEX_MASTER_KEY=$MASTER_KEY
CORTEXDB_MASTER_SECRET=$MASTER_SECRET

# Database passwords (auto-generated)
POSTGRES_PASSWORD=$PG_PASS
REDIS_PASSWORD=$REDIS_PASS
STREAM_PASSWORD=$STREAM_PASS

# CORS
CORTEX_CORS_ORIGINS=https://$DOMAIN

# Dashboard API URL
NEXT_PUBLIC_API_URL=https://$DOMAIN

# LLM Providers
OLLAMA_BASE_URL=http://host.docker.internal:11434
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Observability
GRAFANA_PASSWORD=$GRAFANA_PASS
CORTEX_METRICS_TOKEN=$METRICS_TOKEN
LOG_FORMAT=json

# Ports (internal, Nginx handles external 80/443)
DASHBOARD_PORT=3000
EOF

chmod 600 "$OUTPUT_PATH"

echo ""
echo "Generated $OUTPUT with production secrets."
echo ""
echo "  Domain:        $DOMAIN"
echo "  Secret key:    ${SECRET_KEY:0:8}...${SECRET_KEY: -4} (${#SECRET_KEY} chars)"
echo "  Admin token:   ${ADMIN_TOKEN:0:8}... (${#ADMIN_TOKEN} chars)"
echo "  PG password:   ${PG_PASS:0:4}... (${#PG_PASS} chars)"
echo ""
echo "Next steps:"
echo "  1. Review and edit: nano $OUTPUT"
echo "  2. Add LLM API keys if needed (ANTHROPIC_API_KEY, OPENAI_API_KEY)"
echo "  3. Generate TLS certs: ./scripts/generate-certs.sh --prod"
echo "  4. Deploy: ./scripts/deploy-prod.sh"
