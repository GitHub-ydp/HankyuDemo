#!/usr/bin/env bash
# 在一次性 docker PG 上跑全套 alembic 迁移 + seed，验证 SQLite→PG 兼容性。
# 用法：bash scripts/verify_pg_migrations.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 兼容 git worktree：优先用仓库根目录下的 .venv，其次向上最多 4 层找
find_venv_python() {
  local dir="$REPO_ROOT"
  local depth=0
  while [ $depth -le 4 ]; do
    if [ -f "${dir}/.venv/bin/python" ]; then
      echo "${dir}/.venv/bin/python"
      return
    fi
    dir="$(cd "${dir}/.." && pwd)"
    depth=$((depth + 1))
  done
  echo ""
}

PYTHON="$(find_venv_python)"
if [ -z "$PYTHON" ]; then
  echo "❌ 找不到 .venv/bin/python（在 ${REPO_ROOT} 及上两级均未找到）"
  exit 1
fi
echo "使用 Python: $PYTHON"

CONTAINER=hankyu_pg_verify
PORT=55432
URL="postgresql+psycopg2://postgres:postgres@localhost:${PORT}/hankyu_hanshin"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

cleanup
docker run -d --name "$CONTAINER" \
  -e POSTGRES_DB=hankyu_hanshin -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -p ${PORT}:5432 postgres:16 >/dev/null
echo "等待 PG 就绪..."
for i in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "==> alembic upgrade head"
cd "${REPO_ROOT}/backend"
DATABASE_URL="$URL" "$PYTHON" -m alembic upgrade head

echo "==> seed_data.py"
cd "${REPO_ROOT}"
DATABASE_URL="$URL" "$PYTHON" scripts/seed_data.py
echo "✅ PG 迁移 + seed 验证通过"
