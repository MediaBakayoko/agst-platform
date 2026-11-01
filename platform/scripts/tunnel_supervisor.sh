#!/usr/bin/env bash
# Supervision du tunnel Cloudflare "quick tunnel" pour AGST OS.
# Redemarre automatiquement en cas de coupure (ces tunnels gratuits
# n'ont aucune garantie de disponibilite -- avertissement Cloudflare
# a chaque demarrage). Ecrit l'URL courante dans tunnel_url.txt et
# un etat de sante dans tunnel_health.txt pour supervision externe.

BACKEND_PORT=8010
CLOUDFLARED="/c/Program Files (x86)/cloudflared/cloudflared"
URL_FILE="$(dirname "$0")/tunnel_url.txt"
HEALTH_FILE="$(dirname "$0")/tunnel_health.txt"
LOG_FILE="$(dirname "$0")/tunnel_supervisor.log"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $1" >> "$LOG_FILE"
}

check_tunnel_alive() {
    local url="$1"
    [ -z "$url" ] && return 1
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url/health" 2>/dev/null)
    [ "$code" = "200" ]
}

start_tunnel() {
    log "Demarrage d'un nouveau tunnel..."
    "$CLOUDFLARED" tunnel --url "http://127.0.0.1:$BACKEND_PORT" > "$(dirname "$0")/cloudflared_raw.log" 2>&1 &
    TUNNEL_PID=$!
    log "Tunnel lance, PID=$TUNNEL_PID, attente de l'URL..."

    local attempts=0
    local url=""
    while [ $attempts -lt 20 ]; do
        url=$(grep -oE 'https://[a-z-]+\.trycloudflare\.com' "$(dirname "$0")/cloudflared_raw.log" 2>/dev/null | head -1)
        if [ -n "$url" ]; then
            break
        fi
        sleep 1
        attempts=$((attempts + 1))
    done

    if [ -z "$url" ]; then
        log "ECHEC: impossible d'obtenir une URL de tunnel apres 20s"
        echo "echec" > "$HEALTH_FILE"
        return 1
    fi

    echo "$url" > "$URL_FILE"
    log "Nouvelle URL de tunnel: $url"
    echo "actif" > "$HEALTH_FILE"
    return 0
}

# Boucle de supervision principale.
while true; do
    current_url=$(cat "$URL_FILE" 2>/dev/null || echo "")

    if ! check_tunnel_alive "$current_url"; then
        log "Tunnel inaccessible (url=$current_url) -- redemarrage"
        echo "redemarrage" > "$HEALTH_FILE"
        # Tuer l'ancien process cloudflared s'il existe encore (pkill
        # absent sur ce shell MSYS -- on cible par nom de process via
        # tasklist/taskkill natifs Windows).
        pid=$(tasklist 2>/dev/null | grep -i cloudflared | awk '{print $2}' | head -1)
        if [ -n "$pid" ]; then
            taskkill /F /PID "$pid" 2>/dev/null
        fi
        sleep 2
        start_tunnel
    fi

    sleep 30
done
