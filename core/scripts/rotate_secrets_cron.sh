#!/bin/bash
#
# Nexus Secret Rotation Cron Script
# Runs every 90 days to rotate internal secrets
#
# This script:
# 1. Rotates internal secrets (SECRET_KEY, ADMIN_JWT_SECRET, etc.)
# 2. Logs the rotation for audit
# 3. Optionally restarts services (if configured)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NEXUS_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$NEXUS_DIR/logs/secret_rotation.log"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

# Create logs directory if it doesn't exist
mkdir -p "$NEXUS_DIR/logs"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting scheduled secret rotation"
log "=========================================="

# Change to nexus directory
cd "$NEXUS_DIR"

# Run the rotation script
if $PYTHON scripts/rotate_secrets.py >> "$LOG_FILE" 2>&1; then
    log "Internal secrets rotated successfully"
else
    log "ERROR: Secret rotation failed!"
    exit 1
fi

# Send notification (macOS)
if command -v osascript &> /dev/null; then
    osascript -e 'display notification "Internal secrets have been rotated. Remember to rotate external API keys (Stripe, Twilio, DigitalOcean)." with title "Nexus Security" subtitle "Secret Rotation Complete"'
fi

log "=========================================="
log "REMINDER: Rotate external secrets manually:"
log "  - Stripe: https://dashboard.stripe.com/apikeys"
log "  - Twilio: https://console.twilio.com"
log "  - DigitalOcean: https://cloud.digitalocean.com/account/api/tokens"
log "=========================================="

# Optional: Restart services if running in Docker
# Uncomment these lines when deployed:
# if command -v docker &> /dev/null; then
#     log "Restarting Nexus services..."
#     docker compose -f "$NEXUS_DIR/docker-compose.yml" restart api worker
#     log "Services restarted"
# fi

log "Secret rotation complete"
