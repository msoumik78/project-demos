#!/bin/sh
# Start order-api twice (platform threads, then virtual threads) and run load/orders.py against each.
# delay-stub must already be listening on port 8081.
# Works with both `sh load/compare.sh` and `./load/compare.sh`.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAR="$ROOT/order-api/target/order-api-1.0.0.jar"
RESULTS="$ROOT/load/results"
mkdir -p "$RESULTS"

if [ -z "${JAVA_HOME:-}" ] && [ -x /usr/libexec/java_home ]; then
  JAVA_HOME="$(/usr/libexec/java_home 2>/dev/null || true)"
fi
if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
  JAVA="$JAVA_HOME/bin/java"
elif command -v java >/dev/null 2>&1; then
  JAVA="$(command -v java)"
else
  echo "Set JAVA_HOME to a JDK 21+ install. 'java' is not on PATH."
  exit 1
fi

if [ ! -f "$JAR" ]; then
  echo "Build order-api first: mvn -f \"$ROOT/order-api/pom.xml\" package -DskipTests"
  exit 1
fi

if ! curl -sf "http://127.0.0.1:8081/delay?ms=1" >/dev/null; then
  echo "delay-stub is not answering on port 8081. Start it and rerun this script."
  exit 1
fi

run_mode() {
  profile="$1"
  echo "Starting order-api profile=$profile"
  if [ "$profile" = "platform" ]; then
    "$JAVA" -jar "$JAR" >"$RESULTS/$profile.log" 2>&1 &
  else
    "$JAVA" -jar "$JAR" --spring.profiles.active="$profile" >"$RESULTS/$profile.log" 2>&1 &
  fi
  pid=$!
  i=0
  while [ "$i" -lt 40 ]; do
    if curl -sf "http://127.0.0.1:8080/actuator/health" >/dev/null; then
      break
    fi
    i=$((i + 1))
    sleep 0.5
  done
  if ! curl -sf "http://127.0.0.1:8080/actuator/health" >/dev/null; then
    echo "order-api did not become healthy; see $RESULTS/$profile.log"
    kill "$pid" 2>/dev/null || true
    exit 1
  fi

  echo "Warmup (40 callers, 5s)"
  python3 "$ROOT/load/orders.py" --vus 40 --duration 5

  echo "Measure (200 callers, 45s)"
  python3 "$ROOT/load/orders.py" --vus 200 --duration 45 | tee "$RESULTS/$profile.txt"
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  sleep 2
}

run_mode platform
run_mode virtual

python3 - "$RESULTS" <<'PY'
import re, sys
from pathlib import Path

results = Path(sys.argv[1])

def p95(name):
    text = (results / f"{name}.txt").read_text()
    match = re.search(r"p95=([0-9.]+)", text)
    if not match:
        raise SystemExit(f"no p95 in {name}.txt")
    return float(match.group(1))

platform = p95("platform")
virtual = p95("virtual")
drop = (platform - virtual) / platform * 100 if platform else 0
print(f"platform p95: {platform:.1f} ms")
print(f"virtual  p95: {virtual:.1f} ms")
print(f"p95 change:   {drop:.1f}% lower with virtual threads")
PY
