# 部署任务书 · 致 Codex（2026-06-02）

> 这是一份**工作交接单**，不是完整运维手册。完整命令以 `DEPLOYMENT.md` 为准，本文件只
> 钉死三件事：**部署哪个 ref、本批次有哪些必做动作、验收到什么程度算过**。
>
> **分工**：开发侧（Claude）出代码 + 本交接单；**Codex 负责在服务器上实施部署**；
> 用户负责传达引导、提供生产密钥、拍板。遇到拿不准的，先问用户，别在生产瞎试。

---

## 1. 部署源（唯一真相）

- **部署 `origin/main`，commit `40651a7`**（`Merge pull request #4`，已含本批全部工作）。
- PR #4 已合并进 main，**不要**再去 checkout 任何 `feature/*` 分支部署。
- 仓库：`https://github.com/GitHub-ydp/HankyuDemo.git`，分支 `main`。

```bash
cd <部署目录>            # 首次部署见 DEPLOYMENT.md §2.2 的 /opt/hankyu
git fetch origin
git checkout main
git pull --ff-only        # 期望 HEAD = 40651a7 或更新
git rev-parse HEAD        # 跟用户核对一致再往下
```

---

## 2. 第一步：先勘察，再决定走「首次」还是「升级」

用户暂未确认目标机是全新还是已有试运行实例。**你先勘察，再二选一，别假设。**

```bash
# 有没有在跑的后端服务？
systemctl status hankyu-backend 2>/dev/null || echo "无 systemd 服务 → 倾向首次部署"
# 有没有已部署的代码目录？
ls -la /opt/hankyu 2>/dev/null && (cd /opt/hankyu && git log --oneline -3)
# 前端静态目录在不在？
ls -la /var/www/hankyu/current 2>/dev/null | head
```

- **若无服务 / 无代码目录** → **首次部署**，照 `DEPLOYMENT.md §2` 从系统依赖一路装到 nginx。
- **若已有在跑的实例** → **升级部署**，照 `DEPLOYMENT.md §3` 一步步来（先 `cp` 备份 SQLite/DB）。
- 拿不准就把勘察结果发给用户，等用户拍板。

---

## 3. 本批次的关键变更 → 决定你必须做哪些动作

这批改动相对上一版 main（`f756b29`），各动作**是否必做**如下：

| 动作 | 本批是否需要 | 说明 / 命令 |
|---|---|---|
| **后端 pip 安装** | **不需要** | `requirements.txt` 本批无变化。仍按 `DEPLOYMENT.md §3.1` diff 确认一次即可。 |
| **alembic 迁移** | **✅ 必做** | 本批新增迁移 `backend/alembic/versions/20260601_0001_air_tier_dims.py`（AirTierRate +4 列）。`cd backend && ../.venv/bin/python -m alembic upgrade head`，确认 `alembic current == heads`。 |
| **字典 reseed** | **✅ 必做** | 本批补了约 22 个港口（ONE 合约覆盖缺口）。跑 `.venv/bin/python scripts/seed_data.py`，以脚本实际打印为准；**ports 应高于旧版 140**，carriers 仍 34。 |
| **前端重新 build + 拷 dist** | **✅ 必做** | 本批改了菜单（Layout）、运价表生成页（RateSheetBuilder：海运/航空审核台动态列、会话级起运/币种、手动添加行）、i18n 三语。`npm run build` → 拷 `dist/` 到 `/var/www/hankyu/current/` → `nginx -s reload`。**少一步浏览器就是旧 bundle。** |
| **后端 restart** | **✅ 必做** | 代码 + 迁移都变了，`sudo systemctl restart hankyu-backend`，确认启动时间晚于本次 pull。 |

---

## 4. 生产 .env（密钥由用户提供，⚠️ 不要照搬 .env.example）

`.env` 不入 git。用户会把生产值线下给你填。**两个最容易翻车的点先讲清：**

### 4.1 AI Provider —— 本系统现在跑「阿里云百炼 · Qwen-VL（视觉）」，不是自托管 vLLM

SP1 的航空元料金抽取要**读微信图（视觉）**，所以生产必须用**视觉模型**且服务器能联网到百炼。
`.env.example` 里的默认值还指向旧的自托管 vLLM（`43.133.197.65`，无视觉）——**照搬会让 SP1 图片抽取直接失败**。

`backend/.env` 的 AI 段请按下面这套配（key 用户给）：

```ini
AI_PROVIDER=vllm
VLLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VLLM_API_KEY=<用户提供的百炼 DashScope Key>
VLLM_MODEL=qwen-vl-max-latest
VLLM_ENABLE_CHAT_TEMPLATE_KWARGS=false   # ★ 百炼必须 false，否则 400
AI_AUTO_NO_THINK=false                    # 非 Qwen3 思考模型，关掉 /no_think 追加
```

> 备注：后端起来后，「系统设置」页可在运行时改 AI 参数（30s 生效，无需重启）。但**首次默认值仍来自 .env**，所以 .env 必须能用。

### 4.2 其余必填项（用户提供值）

| key | 位置 | 说明 |
|---|---|---|
| `DATABASE_URL` | `backend/.env` | SQLite 留默认 / PostgreSQL 填 `postgresql://...`。切 DB 后**必须**重跑 `seed_data.py`。 |
| `UPLOAD_DIR` | `backend/.env` | 生产**写绝对路径** `/var/lib/hankyu/uploads`，并 `chown`/`chmod` 可写（见 §5、§2.3）。 |
| `APP_ENV` / `DEBUG` | `backend/.env` | 生产 `APP_ENV=production` / `DEBUG=false`。 |
| `EMAIL_ADDRESS` / `EMAIL_PASSWORD` | `backend/.env` | 邮件检索 Demo 用，用户提供。 |
| `VITE_API_BASE_URL` | **`frontend/.env`（需新建，仓库无此文件）** | 例 `https://<域名>/api/v1`。**改完必须重新 `npm run build`**，否则等于没改（DEPLOYMENT.md §4.7 是踩过的坑）。 |

> 操作建议：用户没给齐之前，先 `cp backend/.env.example backend/.env` 起草，把上面要回填的项标注清楚，发回用户确认，**不要拿占位 key 去跑**。

---

## 5. 执行顺序速查

- **首次**：DEPLOYMENT.md §2.1 系统依赖 → §2.2 clone+venv → §2.3 .env（按本文 §4）→ §2.4 alembic+seed → §2.5 前端 build → §2.6 systemd → §2.7 nginx。
- **升级**：DEPLOYMENT.md §3 顺序走，**本批对应**：§3.1 跳过 pip（无变化）→ §3.2 跑 alembic（有新迁移）→ §3.3 跑 seed（港口补全）→ §3.4 前端必 build → §3.5 restart → §3.6 烟雾测试。
- 生产红线（DEPLOYMENT.md §10）：**不覆盖生产 `.env`、不 `rm -rf uploads`、升级前先备份 DB、不在生产 `git reset --hard`。**

---

## 6. 验收清单（做完逐条核，过不了别报"完成"）

**通用（DEPLOYMENT.md §3.6）**
- [ ] `curl -s http://127.0.0.1:8000/api/v1/health` → 200
- [ ] `carriers?only_used=false` ≥ 34；`freight-rates/stats` 有数
- [ ] `alembic current == heads`；`systemctl status` 启动时间晚于本次 pull
- [ ] 浏览器 Network 里 `main-*.js` 的 hash 与服务器 `dist/` 一致（确认前端是新 bundle）

**本批专属（这几条是这次部署的意义所在，必须实测）**
- [ ] **运营菜单**：「运价表生成」(/rate-sheet) 出现在「仪表盘」之后第 2 位
- [ ] **SP1 航空 AI 抽取实走**：在服务器上（能连百炼）跑 `backend/scripts/smoke_air_ai_extract.py`，对真实微信图能抽出多维档位行（重量档 × 泡比 × 货类/包装 × 航司）。⚠️ 本批 SP1 此前只在本机做过单测、未做过真机 AI 实走（开发机 dashscope 不可达），**这是首次真机验证，必须跑通或如实回报失败**
- [ ] **海运审核台**：上传海运 Excel → 审核台能见 40HC/币种等动态列 → 改价后「采用」能落库（旧版有"改价不入库/40HC 不可见"的 bug，本批修了，要复测）
- [ ] **港口字典**：导入 ONE 合约 PDF，"未匹配"数应大幅下降（旧版 3997 → 目标 0 附近）
- [ ] **日本段 JPY**：运价表会话起运港选 NRT/币种 JPY → 审核台「＋手动添加行」手录 → 入库 → Customer A 投标包 単価(円/kg) 能回填

---

## 7. 回滚

按 `DEPLOYMENT.md §9`：`git checkout <上一个稳定 commit>`（上一版稳定点是 `f756b29`）→ 重启后端 + 重 build 前端 + reload nginx；若已 `alembic upgrade` 过，必要时 `alembic downgrade -1`。**回滚前先备份当前 DB。**

---

## 8. 有疑问找谁

- 代码 / 迁移 / 本批行为问题 → 回报用户，由用户转给开发侧（Claude）。
- 服务器 / 域名 / 密钥 / DB 选型 → 用户提供。
- 任何"修了还是不好使" → 先把 `DEPLOYMENT.md §4` 从上往下排一遍再上报。
