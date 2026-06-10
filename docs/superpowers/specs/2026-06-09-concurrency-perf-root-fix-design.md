# 并发超时/变慢 根治方案设计

- 日期：2026-06-09
- 状态：已与用户确认设计，待写实施计划
- 背景问题：多用户同时使用时，前端连后端**经常超时或很慢**
- 关联记忆：`concurrency-threadpool-fix`（2026-06-08 P0-1 已修，本设计处理遗留的 P1）、`pivot-2tenant-monthly-billing`（2 客户生产化）

---

## 1. 问题与根因诊断

「多人用就超时/变慢」不是单点 bug，是**部署架构在并发下的结构性瓶颈**。逐层取证后定位到三个串联的「单车道」：

| # | 根因 | 证据（file:line） | 机制 |
|---|------|------------------|------|
| ① | **SQLite 全库写锁 + 无 WAL** | `core/database.py:11-23`（只设 `foreign_keys=ON`，无 `journal_mode=WAL`/`busy_timeout`）；`.env: DATABASE_URL=sqlite:///./hankyu_hanshin.db` | rollback 日志模式下写者阻塞读者。一个人做大批运价导入（几千行一事务）锁住全库，所有人的查询都等 → 瞬时全站变慢 |
| ② | **AI 长任务占满共享线程池/GPU** | `services/ai_client.py:201`（同步 `httpx.post(timeout=300)`）；`.env: AI_TIMEOUT_SECONDS=300`；单 uvicorn 进程无 `--workers`（`DEPLOYMENT.md:140`），anyio 默认线程池仅 40 容量（代码无覆盖） | AI 请求同步阻塞、最长占线程槽 300s，且都堵在单 GPU 后。并发触发时线程槽/GPU 队列被长期占住，连查字典这种轻请求都排队 → 普遍超时 |
| ③ | **超时三层倒挂** | 后端 httpx 300s（`.env`）＞ 前端 axios 120~180s（`api.ts`）＞ nginx `proxy_read_timeout 120s`（`DEPLOYMENT.md:181`） | nginx 120s 是最短一环，长任务被它先掐断返回 504，用户看到「超时」，但后端线程仍空转到 300s 不释放资源 |

上次（2026-06-08）只修了 P0-1（5 个 async 长任务路由甩 `run_in_threadpool`，消除 event loop 冻死），缓解了「卡死」，但上面三个串行点没动，所以「并发变慢/超时」仍在。

## 2. 关键决策记录（已与用户确认）

1. **根治范围**：根治三个根因 = PG 迁移 + AI 异步化 + AI 限流 + 超时对齐，**保持单 worker**。
   - **不做**状态外置 + 多 worker：对 2 客户体量是过度工程（YAGNI）。瓶颈是 I/O 等待不是算力；做完异步化后单 worker 够用。体量真涨上来再单独立项。
2. **生产 DB 现状**：SQLite → 需要 PG 迁移。
3. **历史数据策略**：**不迁历史**。干净 PG 跑 `alembic upgrade head` + `seed_data.py`，客户重导运价。迁移风险最低、无需写数据搬运脚本。前提：库里无「丢了会痛」的真实数据（用户已确认）。
4. **AI 异步化采用最小侵入法**：DB 表 `async_task` 只做进度信令，AI 结果仍写现有内存 `_parse_cache`，下游 `preview/confirm` 链路一行不改（单 worker 下内存态安全）。

## 3. 目标与非目标

**目标**：消除①②③三个并发根因。做完后单 worker 可稳定支撑 2 客户多人并发，轻请求不再被 AI/导入拖垮，长任务不再触发超时倒挂。

**非目标（本轮明确不做）**：
- 状态外置（`_draft_batches` / 做表 `_sessions` / `_parse_cache`+`_inbox_email_cache` / `TOKEN_STORE`）+ 多 worker —— YAGNI。
- `rate-sheet` preview/download 上万行大 JSON 的传输慢 —— 那是**单用户大数据量**问题，不是并发问题，仅顺带受益于超时对齐；深度优化（流式/分页）留作后续。
- 多租户/鉴权 —— 与本问题正交，另行立项（见 `concurrency-threadpool-fix` 的 P1④）。

## 4. 模块设计

### 改动地图
```
后端
├── core/database.py         模块A: PG连接池(pool_pre_ping/recycle), 保留SQLite分支
├── models/async_task.py     模块B: 新增「异步任务」表(仅信令)
├── services/async_runner.py 模块B/C: 独立ThreadPoolExecutor(兼AI限流)
├── api/v1/tasks.py          模块B: GET /tasks/{id} 轮询端点
├── api/v1/ai_parse.py       模块B: 4个AI端点改「提交即返回」
├── api/v1/rate_sheet.py     模块B: /{id}/files 改异步
├── api/v1/bidding.py        模块B: /auto-fill 改异步
├── .env / alembic           模块A: DATABASE_URL切PG + 干净PG迁移验证
前端
├── services/api.ts          模块B: 6处调用改「提交+轮询」; 模块D: 去长超时
├── hooks/useAsyncTask.ts    模块B: 统一轮询hook
nginx (DEPLOYMENT.md)        模块D: proxy_read_timeout 120s→60s
```

### 模块 A — PostgreSQL 迁移（根治①写锁）
- `.env`：`DATABASE_URL` 切 `postgresql://...`（docker-compose 的 PG 已就绪，`psycopg2-binary` 已在依赖）。
- `core/database.py`：PG 分支配置连接池 `pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800`；**保留 SQLite 分支**，靠 `DATABASE_URL` 切换（本地开发不强制装 PG）。
- 数据：不迁历史。干净 PG 跑 `alembic upgrade head` + `scripts/seed_data.py`（期望 34 船司 / 140 港口），客户重导运价。
- **关键验证（本模块唯一真风险）**：在干净 PG 上跑全套 alembic 迁移。SQLite 容忍但 PG 严格的写法（Boolean / Enum native type / JSON / 自增序列）必须预演通过。
- **过渡缓解**（迁移上线前的窗口期，可选）：先给 SQLite 加 `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000`，立刻缓解写锁；PG 上线后此分支自然不走。

### 模块 B — AI 长任务异步化（根治②，让长任务不占 HTTP 连接/线程槽）
**最小侵入原则：只在「入口」包一层任务信令，下游链路不动。**

- 新表 `async_task`：`id(uuid) / task_type / status(pending→running→succeeded/failed) / progress(int) / batch_id / error / created_at / updated_at / expires_at`。**只存进度信令，不存大结果。**
- AI 解析真实结果**仍写现有内存 `_parse_cache`**（`ai_parse.py:23/45/95/222/295`）——单 worker 下内存态安全，**所以 `_parse_cache` / `/ai/confirm` 核心链路一行不改**。
- 提交端点（如 `/ai/parse-wechat-image`）流程：
  1. 落盘上传文件 → 建 `async_task(pending)` → 提交给后台执行器 → **立即返回 `{task_id}`**（HTTP 202）。
  2. 后台任务跑完 → 结果进 `_parse_cache` → `async_task` 标 `succeeded` 并带 `batch_id`（失败标 `failed` + `error`）。
- 轮询端点 `GET /tasks/{id}`：返回 `status / progress / batch_id / error`。
- 前端轮询到终态 → 取 `batch_id` → **走原有 preview/confirm 流程**。
- **异步化范围 = 6 个真正调 AI 的端点**：
  1. `/ai/parse-wechat-image`
  2. `/ai/parse-email-text`
  3. `/ai/parse-inbox-email`
  4. `/ai/parse-inbox-attachment`
  5. `/rate-sheet/{session_id}/files`（AI 抽取做表）
  6. `/bidding/auto-fill`
- **不异步化**（保持同步，仅做模块 D 超时对齐）：`/rate-batches/upload`（Excel 解析，快）、`/ai/upload-msg-file`（.msg 解析）、`/ai/inbox-emails`（IMAP 拉取）、`/rate-sheet/{id}/preview|download`（大 JSON，数据量问题非 AI）。

### 模块 C — AI 并发限流（合并进模块 B）
- 后台执行器用**独立 `ThreadPoolExecutor(max_workers=N)`**，与 FastAPI 请求线程池物理隔离。`N` 可配（`app_settings` 或 `settings`，默认 2–3，匹配单 GPU 并发能力）。
- 它**同时是限流器 + 任务队列**：超过 `N` 个 AI 任务自动排队；因是后台任务，前端只看到「排队中/处理中」，**不占 HTTP 连接、不吃请求线程池**。轻请求永远有线程槽 → 全站不再被 AI 拖垮。

### 模块 D — 超时三层对齐（根治③）
- 异步化后所有 HTTP 请求都变短（提交快返回 + 短轮询），长超时自然消失。
- nginx `proxy_read_timeout` 120s → 60s；前端 axios 去掉 120/180s 长超时回归默认（提交端点/轮询端点都短）；后端 `ai_timeout_seconds` 仅约束后台任务，不再影响 HTTP。
- 例外：`rate-sheet preview/download` 大 JSON 保持现有 180s 前端超时 + nginx 对应放宽（非本轮重点，数据量问题）。

## 5. 测试策略
- **模块 A**：干净 PG 跑全套 alembic + `seed_data.py` + 端到端导一份运价（烟雾）；断言 34/140 字典数。
- **模块 B/C**：
  - `async_task` 状态机单测（pending→running→succeeded/failed 流转）。
  - **守卫测试**：提交端点立即返回、不阻塞（仿上次 event-loop 探针思路，断言提交耗时远小于任务耗时）。
  - 限流测试：`N+1` 个任务时第 `N+1` 个在执行器队列等待。
  - 轮询端点：未知 task_id → 404；终态返回 batch_id。
- **回归**：现有 452 测试全过 + 新增。
- **前端**：`npm run lint` + `npm run build` 通过（无 `npm test`）。

## 6. 上线顺序（增量、每步可回滚）
1. **模块 D 超时对齐**（纯配置、零风险）→ 立刻缓解。
2. **模块 A PG 迁移**（停机窗口：备份 SQLite → 切 `DATABASE_URL` → alembic + seed → 客户重导）→ 回滚 = 切回 SQLite `DATABASE_URL`。
3. **模块 B+C AI 异步化 + 限流**（前后端一起，测试守卫 + 旧端点保留一版灰度）→ 回滚 = 前端切回同步调用。

## 7. 风险与回滚
| 风险 | 缓解 | 回滚 |
|------|------|------|
| PG alembic 不兼容 | 干净 PG 预演全套迁移 | 切回 SQLite `DATABASE_URL` |
| AI 异步化改动面广（前端 6 处 + hook） | 测试守卫 + 最小侵入（下游不动）+ 旧端点保留一版 | 前端切回同步端点 |
| `_parse_cache` 内存态在单 worker 假设下才安全 | 设计中明确「不开多 worker」；若未来开 worker 必须先做状态外置（已在非目标记录） | —— |

## 8. 验收标准
- 并发 5+ 用户混合操作（查询 + 导入 + AI 解析）时，轻请求（查字典/列表）P95 延迟不被 AI/导入拖垮。
- AI 解析期间，前端不再出现 nginx 504；用户看到「处理中」进度而非长时间转圈后超时。
- 大批运价导入期间，其他用户查询不被阻塞（PG 行级锁 / 读写不互锁）。
- 现有 452 测试 + 新增守卫测试全绿。
