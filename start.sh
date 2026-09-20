#!/usr/bin/env bash
# Local launcher: console output only; stops only processes it starts.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MODEL="${TIANJI_MODEL_PATH:-$HOME/models/Qwen3.5-9B/Qwen3.5-9B-Q4_K_M.gguf}"
PORT="${TIANJI_PORT:-8787}"
MODEL_PORT="${TIANJI_MODEL_PORT:-18789}"
DATA_DIR="${TIANJI_DATA_DIR:-$ROOT/.local-data}"
GPU_LAYERS="${TIANJI_GPU_LAYERS:-99}"
WITH_MODEL=1
PIDS=()

usage() {
    printf '%s\n' \
        'Usage: ./start.sh [--no-model] [--model /path/to/model.gguf]' \
        'Default: start the local model and Contingent; Ctrl+C stops both.' \
        'Environment: TIANJI_MODEL_PATH, TIANJI_PORT, TIANJI_MODEL_PORT,' \
        '             TIANJI_DATA_DIR, TIANJI_GPU_LAYERS (0 for CPU).' \
        'No model downloads, background installation or log files.'
}
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
while (($#)); do
    case "$1" in
        --no-model) WITH_MODEL=0; shift ;;
        --model) (($# >= 2)) || die '--model requires a path'; MODEL="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unknown argument: $1" ;;
    esac
done
for cmd in uv npm curl; do command -v "$cmd" >/dev/null || die "Missing command: $cmd"; done
for port in "$PORT" "$MODEL_PORT"; do
    [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && ((port <= 65535)) || die "Invalid port: $port"
done
if ((WITH_MODEL)); then
    command -v llama-server >/dev/null || die 'Missing llama-server; install it or use --no-model'
    [[ -r "$MODEL" && -f "$MODEL" ]] || die "Model not found: $MODEL (use --model or --no-model)"
    [[ "$GPU_LAYERS" =~ ^[0-9]{1,3}$ ]] || die 'TIANJI_GPU_LAYERS must be 0..999'
    [[ "$PORT" != "$MODEL_PORT" ]] || die 'API and model ports must differ'
fi
port_free() {
    if (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then
        die "Port $1 is occupied; stop its owner or select another port. Nothing was stopped."
    fi
}
port_free "$PORT"
if ((WITH_MODEL)); then port_free "$MODEL_PORT"; fi

cleanup() {
    local pid alive deadline
    trap - EXIT INT TERM
    for pid in "${PIDS[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
    deadline=$((SECONDS + 10))
    while ((SECONDS < deadline)); do
        alive=0
        for pid in "${PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then alive=1; fi
        done
        ((alive)) || break
        sleep 0.2
    done
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid" 2>/dev/null || true; fi
        wait "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Preparing backend and web…\n'
uv sync --project backend --locked
# Always reconcile dependencies with the lockfile, including existing installations.
npm --prefix web ci
npm --prefix web run build
# Check again after dependency installation/build before spawning anything.
port_free "$PORT"
if ((WITH_MODEL)); then port_free "$MODEL_PORT"; fi

wait_ready() {
    local pid="$1" url="$2" label="$3" deadline=$((SECONDS + 120))
    while ((SECONDS < deadline)); do
        kill -0 "$pid" 2>/dev/null || die "$label exited during startup; see console output above"
        if curl --noproxy '*' --silent --fail --max-time 2 "$url" >/dev/null; then
            kill -0 "$pid" 2>/dev/null || die "$label exited during startup"
            return
        fi
        sleep 0.25
    done
    die "$label did not become ready within 120 seconds"
}

# Restrict newly created data directories, without chmod or rewriting existing data.
(umask 077; mkdir -p -- "$DATA_DIR")

if ((WITH_MODEL)); then
    printf 'Loading local model: %s\n' "$MODEL"
    llama-server --model "$MODEL" --host 127.0.0.1 --port "$MODEL_PORT" \
        --alias tianji-local --ctx-size 8192 --parallel 1 --gpu-layers "$GPU_LAYERS" \
        --reasoning off --log-disable &
    MODEL_PID=$!
    PIDS+=("$MODEL_PID")
    wait_ready "$MODEL_PID" "http://127.0.0.1:$MODEL_PORT/health" 'Local model'
    export TIANJI_LOCAL_MODEL_URL="http://127.0.0.1:$MODEL_PORT"
    export TIANJI_LOCAL_MODEL_NAME=tianji-local
else
    # Do not accidentally inherit a provider when manual-only mode was requested.
    unset TIANJI_LOCAL_MODEL_URL TIANJI_LOCAL_MODEL_NAME
fi

backend/.venv/bin/python -m tianji_lab serve --host 127.0.0.1 --port "$PORT" \
    --data-dir "$DATA_DIR" &
API_PID=$!
PIDS+=("$API_PID")
wait_ready "$API_PID" "http://127.0.0.1:$PORT/health" 'Contingent'
printf '\nContingent ready: http://127.0.0.1:%s\n' "$PORT"
if [[ -n "${TIANJI_TOKEN:-}" ]]; then
    printf 'Connect with your existing TIANJI_TOKEN (not printed).\n'
else
    printf 'Token file: %s/token (paste its contents into the web connection form).\n' "$DATA_DIR"
fi
printf 'Ctrl+C stops all services started by this launcher.\n'
if wait -n "${PIDS[@]}"; then
    die 'A service stopped unexpectedly; shutting down the remaining service'
else
    status=$?
    printf 'A service exited with status %s; shutting down.\n' "$status" >&2
    exit "$status"
fi
