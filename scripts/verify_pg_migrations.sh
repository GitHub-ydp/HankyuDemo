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

# 核心表（carriers/ports/freight_rates/lanes 等）不在 alembic 迁移链里，
# 一直由 init_db()（= Base.metadata.create_all）建表。
# 若直接用 alembic upgrade head，最早的迁移会 FK 引用 ports 表但该表还不存在，PG 严格模式下直接失败。
# 正确顺序：先 create_all 建全表 → 再 stamp head 标记版本（避免日后 upgrade 重复建表）→ 最后 seed。
echo "==> create_all（建全部表，SQLAlchemy 按 FK 依赖自动排序）"
cd "${REPO_ROOT}/backend"
DATABASE_URL="$URL" "$PYTHON" -c "from app.core.database import init_db; init_db(); print('create_all OK')"

echo "==> alembic stamp head（标记当前版本为最新，不重复执行 DDL）"
DATABASE_URL="$URL" "$PYTHON" -m alembic stamp head

echo "==> seed_data.py"
cd "${REPO_ROOT}"
DATABASE_URL="$URL" "$PYTHON" scripts/seed_data.py
echo "✅ PG 初始化（create_all + stamp + seed）验证通过"
