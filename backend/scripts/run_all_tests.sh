#!/usr/bin/env bash
# run_all_tests.sh — Corre todos los test_*.py en orden.
# Sigue corriendo aunque alguno falle; reporta resumen al final.
# Exit 0 si todos pasan, Exit 1 si alguno falla.
#
# Uso:
#   cd backend
#   bash scripts/run_all_tests.sh
#
# Variables de entorno útiles:
#   TEST_DATABASE_URL  — BD alternativa (los scripts la toman automáticamente)
#   APP_ENV=test       — Omite checks que llaman a Anthropic/Claude
#   SKIP_TESTS         — Nombres de archivos separados por coma a omitir
#                        Ej: SKIP_TESTS=test_rag.py,test_celery.py

set -o pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPTS_DIR")"
PYTHON="${BACKEND_DIR}/.venv/bin/python"

# ── Colores ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: Python no encontrado en $PYTHON"
    echo "       Corre: cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# ── Descubrir tests ────────────────────────────────────────────────────────────
# Orden estable: primero infraestructura, luego sprints en orden cronológico
ORDERED_TESTS=(
    test_rls.py
    test_registration.py
    test_nomenclatura.py
    test_webhook.py
    test_handoff.py
    test_meta_leads.py
    test_qualification.py
    test_sprint5.py
    test_sprint6.py
    test_sprint8b.py
    test_billing.py
    test_celery.py
    test_rag.py
    test_roi.py
    test_pipeline_api.py
    test_pipeline_ai.py
    test_onboarding.py
    test_bot_config_from_onboarding.py
    test_dashboard.py
    test_deals.py
    test_pipeline.py
    test_stage_probability.py
    test_deal_owner.py
    test_stage_history_endpoint.py
)

# Añadir cualquier test_*.py no listado arriba (para no olvidar nuevos)
for f in "$SCRIPTS_DIR"/test_*.py; do
    name="$(basename "$f")"
    found=0
    for t in "${ORDERED_TESTS[@]}"; do
        [ "$t" = "$name" ] && found=1 && break
    done
    [ $found -eq 0 ] && ORDERED_TESTS+=("$name")
done

# ── Parsear SKIP_TESTS ────────────────────────────────────────────────────────
IFS=',' read -ra SKIP_LIST <<< "${SKIP_TESTS:-}"

should_skip() {
    local name="$1"
    for s in "${SKIP_LIST[@]}"; do
        [ "$s" = "$name" ] && return 0
    done
    return 1
}

# ── Runner ────────────────────────────────────────────────────────────────────
passed_tests=()
failed_tests=()
skipped_tests=()

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Walix CI — run_all_tests.sh"
echo "  Backend: $BACKEND_DIR"
echo "  Python:  $("$PYTHON" --version 2>&1)"
[ -n "${TEST_DATABASE_URL:-}" ] && echo "  BD:      TEST_DATABASE_URL"
[ "${APP_ENV:-}" = "test" ]     && echo "  Modo:    CI (Claude omitido)"
echo "════════════════════════════════════════════════════════"
echo ""

for test_name in "${ORDERED_TESTS[@]}"; do
    test_path="$SCRIPTS_DIR/$test_name"

    if [ ! -f "$test_path" ]; then
        continue
    fi

    if should_skip "$test_name"; then
        echo -e "${YELLOW}⏭  SKIP${NC}  $test_name"
        skipped_tests+=("$test_name")
        continue
    fi

    echo -e "▶  Running $test_name …"
    # Corre el script desde backend/ con timeout de 120s
    # Compatible macOS (gtimeout de coreutils) y Linux (timeout)
    TIMEOUT_CMD=""
    if command -v gtimeout &>/dev/null; then
        TIMEOUT_CMD="gtimeout 120"
    elif command -v timeout &>/dev/null; then
        TIMEOUT_CMD="timeout 120"
    fi
    (
        cd "$BACKEND_DIR"
        $TIMEOUT_CMD "$PYTHON" "scripts/$test_name" 2>&1
    )
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓  PASS${NC}  $test_name"
        passed_tests+=("$test_name")
    elif [ $exit_code -eq 124 ] || [ $exit_code -eq 143 ]; then
        echo -e "${RED}✗  FAIL${NC}  $test_name  (timeout 120s)"
        failed_tests+=("$test_name [TIMEOUT]")
    else
        echo -e "${RED}✗  FAIL${NC}  $test_name  (exit $exit_code)"
        failed_tests+=("$test_name")
    fi
    echo ""
done

# ── Resumen ────────────────────────────────────────────────────────────────────
total=$(( ${#passed_tests[@]} + ${#failed_tests[@]} + ${#skipped_tests[@]} ))

echo "════════════════════════════════════════════════════════"
echo "  RESUMEN"
echo "  Total:   $total scripts"
echo -e "  ${GREEN}Pasaron:${NC} ${#passed_tests[@]}"
echo -e "  ${RED}Fallaron:${NC} ${#failed_tests[@]}"
[ ${#skipped_tests[@]} -gt 0 ] && echo "  Omitidos: ${#skipped_tests[@]}"

if [ ${#failed_tests[@]} -gt 0 ]; then
    echo ""
    echo -e "  ${RED}Scripts con fallos:${NC}"
    for f in "${failed_tests[@]}"; do
        echo "    ✗ $f"
    done
fi
echo "════════════════════════════════════════════════════════"
echo ""

[ ${#failed_tests[@]} -eq 0 ]
