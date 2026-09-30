cd ~/yash/desktop/paperclip

set -e

CONTAINER="my-paperclip"
IMAGE="paperclip:latest"
VOLUME="paperclip_data"
ENV_FILE="$PWD/.paperclip.env"

# ------------------------------------------------------------
# 1. Create permanent secrets/config once
# ------------------------------------------------------------

if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
BETTER_AUTH_SECRET=$(openssl rand -hex 32)
PAPERCLIP_AGENT_JWT_SECRET=$(openssl rand -hex 32)
PAPERCLIP_TOOL_ACTION_SIGNING_SECRET=$(openssl rand -hex 32)

HOST=0.0.0.0
PORT=3100
PAPERCLIP_HOME=/paperclip

PAPERCLIP_DEPLOYMENT_MODE=authenticated
PAPERCLIP_DEPLOYMENT_EXPOSURE=private

PAPERCLIP_PUBLIC_URL=http://localhost:8080
PAPERCLIP_AUTH_PUBLIC_BASE_URL=http://localhost:8080
BETTER_AUTH_URL=http://localhost:8080

PAPERCLIP_AGENT_JWT_TTL_SECONDS=3600
EOF

  chmod 600 "$ENV_FILE"
  echo "Created permanent config: $ENV_FILE"
else
  echo "Using existing permanent config: $ENV_FILE"
fi

# ------------------------------------------------------------
# 2. Make sure persistent volume exists
# ------------------------------------------------------------

docker volume create "$VOLUME" >/dev/null

# ------------------------------------------------------------
# 3. Remove only the container
#    DO NOT remove the volume
# ------------------------------------------------------------

docker rm -f "$CONTAINER" 2>/dev/null || true

# ------------------------------------------------------------
# 4. Start Paperclip with persistent data + correct auth
# ------------------------------------------------------------

docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --env-file "$ENV_FILE" \
  -p 8080:3100 \
  -v "$VOLUME:/paperclip" \
  "$IMAGE"

# ------------------------------------------------------------
# 5. Wait for Paperclip to fully start
# ------------------------------------------------------------

echo
echo "Waiting for Paperclip..."

for i in $(seq 1 60); do
  if curl -fsS http://localhost:8080/api/health >/dev/null 2>&1; then
    echo "Paperclip is READY."
    break
  fi

  echo "Starting... $i/60"
  sleep 2
done

# ------------------------------------------------------------
# 6. Verify important environment variables
# ------------------------------------------------------------

echo
echo "===== CONFIG CHECK ====="

docker exec "$CONTAINER" sh -c '
echo "HOST=$HOST"
echo "PORT=$PORT"
echo "PAPERCLIP_HOME=$PAPERCLIP_HOME"
echo "PAPERCLIP_PUBLIC_URL=$PAPERCLIP_PUBLIC_URL"

if [ -n "$PAPERCLIP_AGENT_JWT_SECRET" ]; then
  echo "PAPERCLIP_AGENT_JWT_SECRET=SET"
else
  echo "PAPERCLIP_AGENT_JWT_SECRET=MISSING"
fi

if [ -n "$BETTER_AUTH_SECRET" ]; then
  echo "BETTER_AUTH_SECRET=SET"
else
  echo "BETTER_AUTH_SECRET=MISSING"
fi

echo
echo "Claude CLI:"
which claude || true

echo
echo "Claude version:"
claude --version 2>/dev/null || true
'

# ------------------------------------------------------------
# 7. Health check
# ------------------------------------------------------------

echo
echo "===== HEALTH ====="
curl -i http://localhost:8080/api/health || true

# ------------------------------------------------------------
# 8. Container status
# ------------------------------------------------------------

echo
echo "===== CONTAINER ====="
docker ps --filter "name=$CONTAINER"

echo
echo "===== PORT ====="
docker port "$CONTAINER"

# ------------------------------------------------------------
# 9. Open GUI
# ------------------------------------------------------------

echo
echo "Opening Paperclip..."
explorer.exe "http://localhost:8080/onboarding" >/dev/null 2>&1 || true

echo
echo "============================================================"
echo "PAPERCLIP READY"
echo "============================================================"
echo
echo "GUI:"
echo "http://localhost:8080"
echo
echo "Onboarding:"
echo "http://localhost:8080/onboarding"
echo
echo "Persistent volume:"
echo "$VOLUME"
echo
echo "Permanent config:"
echo "$ENV_FILE"
echo
echo "============================================================"
echo
echo "IMPORTANT:"
echo "Do NOT delete $VOLUME."
echo "Do NOT delete $ENV_FILE."
echo
