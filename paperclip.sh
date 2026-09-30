# ============================================================
# PAPERCLIP - COMPLETE RESET + PERMANENT DOCKER SETUP
# ============================================================

set -e

CONTAINER="my-paperclip"
IMAGE="paperclip:latest"
VOLUME="paperclip_data"
HOST_PORT="8080"

cd "$HOME/yash/desktop/paperclip"

echo
echo "============================================================"
echo "1. REMOVE OLD PAPERCLIP"
echo "============================================================"

docker rm -f "$CONTAINER" 2>/dev/null || true
docker volume rm "$VOLUME" 2>/dev/null || true
docker image rm -f "$IMAGE" 2>/dev/null || true

echo
echo "Old Paperclip container / volume / image removed."

echo
echo "============================================================"
echo "2. BUILD PAPERCLIP AGAIN"
echo "============================================================"

docker build --target production -t "$IMAGE" . \
  || docker build -t "$IMAGE" .

echo
echo "Paperclip image built."

echo
echo "============================================================"
echo "3. CREATE PERSISTENT VOLUME"
echo "============================================================"

docker volume create "$VOLUME" >/dev/null

echo "Persistent volume: $VOLUME"

echo
echo "============================================================"
echo "4. GENERATE PERMANENT INSTANCE SECRETS"
echo "============================================================"

BETTER_AUTH_SECRET="$(openssl rand -hex 32)"
TOOL_SIGNING_SECRET="$(openssl rand -hex 32)"

echo "Secrets generated."

echo
echo "============================================================"
echo "5. START PAPERCLIP"
echo "============================================================"

docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  -p "$HOST_PORT:3100" \
  -e HOST=0.0.0.0 \
  -e PORT=3100 \
  -e PAPERCLIP_HOME=/paperclip \
  -e BETTER_AUTH_SECRET="$BETTER_AUTH_SECRET" \
  -e PAPERCLIP_TOOL_ACTION_SIGNING_SECRET="$TOOL_SIGNING_SECRET" \
  -v "$VOLUME:/paperclip" \
  "$IMAGE"

echo
echo "Container started."
echo
docker ps --filter "name=$CONTAINER"

echo
echo "============================================================"
echo "6. WAIT FOR PAPERCLIP TO FULLY START"
echo "============================================================"

READY=0

for i in $(seq 1 60); do
    if docker exec "$CONTAINER" \
        node -e "fetch('http://127.0.0.1:3100/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
        >/dev/null 2>&1
    then
        READY=1
        break
    fi

    echo "Waiting for Paperclip... $i/60"
    sleep 2
done

if [ "$READY" != "1" ]; then
    echo
    echo "Paperclip did not become ready."
    echo
    docker logs --tail 200 "$CONTAINER"
    exit 1
fi

echo
echo "Paperclip is READY."

echo
echo "============================================================"
echo "7. OPEN PAPERCLIP GUI"
echo "============================================================"

echo "Opening: http://localhost:$HOST_PORT/onboarding"

explorer.exe "http://localhost:$HOST_PORT/onboarding" \
    >/dev/null 2>&1 || true

sleep 5

echo
echo "============================================================"
echo "8. WAIT FOR CLAUDE SIGN-IN ATTEMPT"
echo "============================================================"
echo
echo "In the browser:"
echo
echo "  Claude"
echo "    -> Start sign-in"
echo
echo "DO NOT click Start sign-in again."
echo
echo "This terminal will automatically detect the UUID generated"
echo "by the current Paperclip connection."
echo

CLAUDE_ROOT="/paperclip/instances/default/ai-local-logins"
FOUND_DIR=""

for i in $(seq 1 300); do

    FOUND_DIR="$(
        docker exec "$CONTAINER" sh -c \
        "find '$CLAUDE_ROOT' -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1" \
        2>/dev/null || true
    )"

    if [ -n "$FOUND_DIR" ]; then
        break
    fi

    echo "Waiting for Claude connection... $i/300"
    sleep 2
done

if [ -z "$FOUND_DIR" ]; then
    echo
    echo "No Claude sign-in attempt was detected within 10 minutes."
    echo
    echo "Paperclip logs:"
    docker logs --tail 200 "$CONTAINER"
    exit 1
fi

CLAUDE_CONFIG_DIR="$FOUND_DIR"

echo
echo "============================================================"
echo "9. CURRENT PAPERCLIP CLAUDE CONNECTION"
echo "============================================================"

echo "CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR"

echo
echo "Starting Claude authentication."
echo "Complete the browser login when prompted."
echo

docker exec "$CONTAINER" sh -c \
    "mkdir -p '$CLAUDE_CONFIG_DIR'"

docker exec -it "$CONTAINER" \
    env CLAUDE_CONFIG_DIR="$CLAUDE_CONFIG_DIR" \
    claude auth login

echo
echo "============================================================"
echo "10. VERIFY CLAUDE CREDENTIALS"
echo "============================================================"

docker exec "$CONTAINER" sh -c "
    echo 'CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR'
    echo
    ls -la '$CLAUDE_CONFIG_DIR'
"

echo
echo "============================================================"
echo "11. WAIT FOR PAPERCLIP TO DETECT LOGIN"
echo "============================================================"

sleep 15

echo
echo "============================================================"
echo "12. FINAL STATUS"
echo "============================================================"

echo
echo "--- CONTAINER ---"
docker ps --filter "name=$CONTAINER"

echo
echo "--- PORT ---"
docker port "$CONTAINER"

echo
echo "--- PAPERCLIP DATA ---"
docker volume inspect "$VOLUME" >/dev/null
echo "Persistent volume: $VOLUME"

echo
echo "--- CLAUDE LOGIN ---"
docker exec "$CONTAINER" sh -c "
    if [ -f '$CLAUDE_CONFIG_DIR/.credentials.json' ]; then
        echo 'Claude credentials: PRESENT'
    else
        echo 'Claude credentials: NOT FOUND'
    fi
"

echo
echo "============================================================"
echo "DONE"
echo "============================================================"
echo
echo "Paperclip GUI:"
echo "http://localhost:$HOST_PORT"
echo
echo "Onboarding:"
echo "http://localhost:$HOST_PORT/onboarding"
echo
echo "Container:"
echo "$CONTAINER"
echo
echo "Persistent Docker volume:"
echo "$VOLUME"
echo
echo "Claude connection directory:"
echo "$CLAUDE_CONFIG_DIR"
echo
echo "============================================================"
