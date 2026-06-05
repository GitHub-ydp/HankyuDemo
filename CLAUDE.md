# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

阪急阪神（Hankyu Hanshin，日本货运代理）入札业务自动化系统。把人工招投标流程
（接收 PKG → 查费率 → 填报 → 内部审核）压缩到分钟级。目前处于 Demo / 实地试运行阶段，
两条主线在并行迭代：**运价导入（step1）** 与 **投标包自动填写（step2）**。

业务术语保持中日英一致，新增文案/翻译都按这张表走，不要自由意译：

| 日文 | 中文 | 英文 |
| ---- | ---- | ---- |
| 入札 | 招标/投标 | Bidding / Tender |
| 見積 | 报价 | Quotation |
| 費率表 | 费率表 | Tariff |
| 航線 | 航线 | Lane |
| 投標包 | 投标包 | PKG (Package) |
| 営業 | 销售/业务 | Sales |
| 混載業者 | 联运商 | Co-loader |
| 現地法人 | 当地子公司 | Local Subsidiary |
| 代理店 | 代理商 | Agent |

## 技术栈（按当前代码，不是规划）

- **后端**：Python 3.10 + FastAPI 0.115 + SQLAlchemy 2.0 + Alembic + pydantic-settings
- **数据库**：本地开发默认 **SQLite**（`backend/hankyu_hanshin.db`），可切换 PostgreSQL 16
  （`docker-compose.yml` 同时拉了 redis，但 redis 当前没被业务代码使用）
- **AI**：默认 vLLM / Qwen3.6（OpenAI 兼容协议，`vllm_base_url`），可切回阿里云百炼或 Anthropic
- **RAG**：ChromaDB + FlagEmbedding（费率向量检索，落地 `data/chroma_db/`）
- **文档处理**：pandas / openpyxl / extract-msg / Pillow
- **前端**：React 19 + TypeScript + Vite 8 + Ant Design v6 + react-router 7 + i18next + axios
- **无 Celery / 无消息队列**：原计划保留，但目前所有任务都在请求线程内同步完成

## 后端架构要点

入口 `backend/app/main.py` → `app/api/v1/router.py` 聚合 10 个子 router
（`carriers / ports / rates / rate_batches / rate_downloads / email_search / ai_parse /
bidding / admin / admin_settings`）。启动时 `init_db()` 会基于
`app/models/base.py:Base.metadata` 自动建表（开发环境用，生产仍走 alembic）。

业务模块按「步骤」划线，**不要混跨**：

```
app/services/
├── step1_rates/          # 运价导入流水线
│   ├── service.py        # 对外入口
│   ├── activator.py      # 决定走哪个 adapter
│   ├── adapters/         # 按运价种类拆：ocean / ocean_ngb / air / kmtc / nvo_fak
│   ├── normalizers.py    # 解析结果 → 统一 entity
│   ├── writers/          # 入库 + 模板回写（含 naming / registry / templates）
│   └── entities.py       # 流水线内部 DTO
├── step2_bidding/        # PKG 自动填写
│   ├── bidding_orchestrator.py
│   ├── customer_identifier.py    # 识别客户 → 选对应 profile
│   ├── customer_profiles/        # 每客户一份适配（已实装 customer_a）
│   ├── rate_matcher.py / rate_repository.py
│   ├── token_store.py / temp_files.py
│   └── entities.py
├── ai_client.py          # 统一 AI 调用，按 ai_provider 路由 vllm / anthropic
├── config_service.py     # 配置缓存层（30s TTL；测试 conftest 会主动 invalidate）
├── email_*.py            # IMAP 抓取 + .msg 解析 + 邮件正文提取
└── rate_parser.py / wechat_image_parser.py / *_service.py
```

数据模型在 `app/models/`：`carrier / port / lane / tariff / freight_rate /
air_freight_rate / air_surcharge / lcl_rate / domestic_rate / surcharge /
import_batch / upload_log / app_settings`。

⚠️ **`app/skills/` 目录是规划期占位，目前为空**。不要在那里写新代码，AI 能力都集中在
`services/ai_client.py`、`services/rate_parser.py`、`services/wechat_image_parser.py`。

## 前端架构要点

`frontend/src/pages/` 共 11 个页面，主线两条：

- **运价管理**：`RateUpload` → `RateList` / `RateBatches` / `RateCompare`，
  配 `CarrierList`、`Settings` 做字典与系统配置
- **投标自动化**：`PkgAutoFill`（上传 PKG → AI 解析 → 预览 → 下载填好的文件） +
  `EmailSearch`（邮件检索 Demo）

所有 API 走 `src/services/api.ts`（axios 实例，基址来自 `import.meta.env.VITE_API_BASE_URL`）。
组件库统一用 **Ant Design v6**，复制外网示例时注意 v6 ↔ v5 的 break change。
i18n 资源在 `src/i18n/`，新增文案必须同时落 zh / ja / en 三份，缺一视为 bug。

## 本地启动

> ⚠️ 后端必须先 `cd backend` 再启动 uvicorn，否则 `.env` 不加载，`DATABASE_URL`
> 会回落到默认 PostgreSQL URL，本地没起 PG 就会直接连接失败。

```bash
# 后端（Mac）— 仓库根已有 .venv（Python 3.10）
cd backend
../.venv/bin/python -m pip install -r requirements.txt        # 首次 / 依赖变更
../.venv/bin/python -m alembic upgrade head                    # DB 迁移
../.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev          # Vite 默认 5173；CORS 已放通 5173~5177

# 字典种子（清库 / 首次部署后跑一次）
cd /Users/zhangdongxu/Desktop/project/阪急阪神
.venv/bin/python scripts/seed_data.py
# 期望：carriers seed: 34 inserted / ports seed: 140 inserted

# 可选：换到 PostgreSQL（与默认 DATABASE_URL 一致）
docker-compose up -d postgres
```

Windows 团队成员把上面所有 `../.venv/bin/python` 换成 `D:\Anaconda3\envs\py310\python.exe`，
完整说明见 `启动说明.md`。

## 测试

```bash
cd backend
../.venv/bin/python -m pytest                                          # 全量
../.venv/bin/python -m pytest tests/test_admin_settings_api.py         # 单文件
../.venv/bin/python -m pytest tests/api_v1/test_admin_reset_reseed.py::TEST_NAME -v
```

`tests/conftest.py` 通过 autouse fixture 在每个测试前后 invalidate
`config_service` 的 30s TTL 缓存，否则跨测会读到陈旧 AI 配置。
**前端没有 `npm test` 脚本**，只有 `npm run lint`（ESLint flat config）和 `npm run build`。

## AI 配置（最容易踩的环境变量）

`backend/.env` 切换 provider：

- `AI_PROVIDER=vllm`（默认）— 走 `VLLM_BASE_URL` + `VLLM_API_KEY` + `VLLM_MODEL`
- `AI_PROVIDER=anthropic` — 走 `ANTHROPIC_API_KEY` + `ANTHROPIC_MODEL`

注意两个坑：

- `AI_AUTO_NO_THINK=true`（默认）会在 user message 末尾自动追加 `/no_think`，
  **只对 Qwen 系生效**；换非 Qwen 模型或回滚百炼时先关掉
- `VLLM_ENABLE_CHAT_TEMPLATE_KWARGS=true` 时请求带 `chat_template_kwargs`，
  阿里云百炼会 400；回滚百炼时务必改 `false`

## 代码规范 / 协作约定

- Python：PEP 8 + type hints，命名 `snake_case`
- TypeScript：函数组件 + Hooks，命名 `camelCase`（组件 `PascalCase`）
- API：RESTful + 统一错误响应；OpenAPI/Swagger 在 `/docs`
- 代码注释 + commit message **用中文**；API 文档英文
- 不要硬编码费率、密钥、邮箱、数据库连接；都走 `backend/.env`（不入 git）
- 改动到 reset/reseed、alembic、上传目录、前端构建产物的代码，提交前必读
  `DEPLOYMENT.md` 的「最常踩的坑」与「升级部署」章节

## 部署 / 运维要点

- 生产部署清单见 `DEPLOYMENT.md`（systemd + nginx + Vite 静态打包）
- `UPLOAD_DIR` 在生产**必须用绝对路径**（如 `/var/lib/hankyu/uploads`），
  否则 uvicorn 切 cwd 后会写到非预期目录
- Admin「清空运价」按钮调 `reseed_dictionaries(db)` 自动回灌 34 船司 / 140 港口字典，
  改 seed 逻辑时同步 `scripts/seed_data.py` 与 `backend/app/api/v1/admin.py`

## 相关文档索引

- `启动说明.md` — Mac / Windows 本地启动速查
- `DEPLOYMENT.md` — 生产部署 + 升级 checklist（必读）
- `AGENTS.md` — OMX 多智能体编排合约（工具生成，勿手改）


## 特殊要求

- 中文回复
