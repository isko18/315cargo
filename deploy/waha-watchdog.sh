#!/bin/bash
# Сторож сессии WhatsApp.
#
# Сессия умирает двумя способами, и второй опаснее:
#   1) статус уезжает из WORKING — видно сразу;
#   2) статус остаётся WORKING, но внутри контейнера отваливается браузерный
#      контекст, и любая отправка падает с "Cannot read properties of undefined
#      (reading 'getChat')". Снаружи всё выглядит здоровым.
#
# Поэтому мало смотреть статус: нужен запрос, который реально идёт в страницу.
# chats?limit=1 — самый дешёвый такой запрос.
#
# Перезапускаем только после двух подряд неудач: одиночный таймаут при нагрузке
# — не повод рвать живую сессию.

set -uo pipefail

API="http://127.0.0.1:3000"
SESSION="${WAHA_SESSION:-default}"
KEY_FILE="/root/.waha_api_key"
STATE="/var/lib/waha-watchdog.fails"
MAX_FAILS=2

log() { logger -t waha-watchdog "$*"; echo "$(date '+%F %T') $*"; }

[ -f "$KEY_FILE" ] || { log "нет $KEY_FILE — пропускаю"; exit 0; }
KEY=$(cat "$KEY_FILE")

fails=$(cat "$STATE" 2>/dev/null || echo 0)
case "$fails" in ''|*[!0-9]*) fails=0 ;; esac

api() { curl -sS --max-time 25 -H "X-Api-Key: $KEY" "$@"; }

restart() {
  log "перезапуск сессии $SESSION: $1"
  api -X POST "$API/api/sessions/$SESSION/restart" >/dev/null 2>&1 \
    || log "перезапуск не удался"
  echo 0 > "$STATE"
}

status=$(api "$API/api/sessions/$SESSION" 2>/dev/null | grep -o '"status":"[A-Z_]*"' | head -1 | cut -d'"' -f4)

if [ -z "$status" ]; then
  log "шлюз не отвечает (контейнер waha упал?)"
  exit 0          # контейнер поднимет docker restart=always, сессию не трогаем
fi

if [ "$status" = "SCAN_QR_CODE" ]; then
  # Перезапуск не поможет: нужен человек с телефоном.
  log "сессия разлогинена — требуется повторное сканирование QR"
  exit 0
fi

if [ "$status" != "WORKING" ]; then
  restart "статус $status"
  exit 0
fi

# Статус здоровый — проверяем, жив ли браузерный контекст.
if api -o /dev/null -w '%{http_code}' "$API/api/$SESSION/chats?limit=1" 2>/dev/null | grep -q '^200$'; then
  [ "$fails" -ne 0 ] && log "контекст восстановился"
  echo 0 > "$STATE"
  exit 0
fi

fails=$((fails + 1))
echo "$fails" > "$STATE"
log "проверка контекста провалена ($fails из $MAX_FAILS)"
[ "$fails" -ge "$MAX_FAILS" ] && restart "браузерный контекст мёртв при статусе WORKING"
exit 0
