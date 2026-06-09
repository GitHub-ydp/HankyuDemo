# 真实登录 + 管理员活动日志 设计文档

- 日期：2026-06-09
- 状态：设计已确认，待写实现计划
- 范围：把当前「纯前端 localStorage 假登录」替换为真实后端认证；新增**仅管理员可见**的活动日志页（用户列表 + 登录历史 + 操作记录）

---

## 1. 背景与现状

当前系统**没有真正的登录**：

- 前端有 `Login.tsx` / `Register.tsx` / `AuthContext.tsx` / `ProtectedRoute.tsx`，但账号与会话**全存浏览器 localStorage**（`hhrh_users` / `hhrh_session`），一台浏览器一份，互不可见，密码是演示用非加密哈希。
- 后端**没有 user 表、没有 `/auth/*` 接口、没有任何登录记录**。`requirements.txt` 无 passlib / jose / bcrypt。
- `upload_logs` 表已有 `uploaded_by`（String，可空）字段，但目前没人填。
- `ProtectedRoute` 只判断「有没有 user」，不区分角色。

因此「最后登录时间」这类数据现在**无处可取**——登录从不碰服务器。本设计补齐真实认证，并以此为数据源做活动日志页。

## 2. 决策记录（已与用户确认）

| 编号 | 决策 | 取值 |
| ---- | ---- | ---- |
| D1 | 隔离模型 | **单部署 + 内部用户**：一套部署内区分管理员/普通用户，共享同一份业务数据。2 个客户用各自独立部署/数据库隔开。**不做**租户级数据隔离 |
| D2 | 账号开通（当前） | **保留开放自助注册**（任何人可注册）。⚠️ 已知风险，用户接受 |
| D3 | 活动日志范围 | **登录历史 + 操作记录**（操作记录复用 `upload_logs`） |
| D4 | 管理员指定 | `.env` 的 `ADMIN_EMAILS` 名单，**实时判定**（不在 DB 存 role，改名单即刻生效） |
| D5 | 会话机制 | **JWT（HS256）**，无状态，前端存 token、axios 带 `Authorization` 头 |
| D6 | 操作记录存储 | **方案 A**：新建 `login_events` 表专记登录历史；操作记录**复用现有两张批次表合并**——`import_batches`（文件导入 activate / 做表入库，已带 `imported_by`+`imported_at`）+ `upload_logs`（`/ai/confirm` 路径，已带 `uploaded_by`+`created_at`）。不建通用 activity_log（YAGNI） |

### D7 关键约束：为「按人头收费 → 管理员指定注册」预留缝（用户重点强调）

业务后续一定按席位（人头）收费，注册方式会从「开放自助」切到「**管理员指定注册**」。本设计**现在就把缝留好**，将来切换只是「改配置 + 加一小块管理 UI」，不返工：

1. **注册模式开关**：新增 `REGISTRATION_MODE` 配置，取值 `open`（当前默认）/ `admin_only`（未来）。
   - `open`：`POST /auth/register` 正常开放。
   - `admin_only`：`POST /auth/register` 直接返回 403（前端隐藏注册入口），账号只能由管理员通过 `POST /admin/users` 创建。
2. **建号逻辑单点收口**：自助注册与（未来）管理员建号**共用同一个** `user_service.create_user()`，差别只在「谁来调、模式校验在哪」。本期只接自助注册这一个调用方；管理员建号端点是下一阶段的小增量（见 §9）。
3. **席位计费友好**：
   - `users` 表即人头**唯一真相源**；`is_active` 软停用（保留历史，不物理删除），停用即释放席位。
   - 活动日志「用户列表」展示**活跃用户数 / 总数**，给计费/对账留口子。
   - `created_at` 保留，便于按入职时间对账。
4. 本期**不实现**席位上限强制、邀请码、邮箱域名白名单——但上述开关与收口让它们成为后续小增量，而非重构。

## 3. 总体架构

```
浏览器 SPA                         FastAPI 后端
─────────                          ─────────────
Login/Register ──POST /auth/* ───▶ auth router ──┐
                                                 ├─▶ user_service (create_user / authenticate)
axios 拦截器 ──Bearer token────────▶ get_current_user (deps)
                                                 ├─▶ users 表（密码哈希 / last_login_at / is_active）
ActivityLog 页 ─GET /admin/*──────▶ get_current_admin ─▶ login_events 表（登录历史）
（仅管理员菜单）                                  └─▶ import_batches + upload_logs（操作记录，合并）
```

- 管理员身份 = 登录用户邮箱 ∈ `ADMIN_EMAILS`（每请求实时判定，非 DB 存储）。
- JWT 无状态：服务端不存 session；登出 = 前端丢弃 token。

## 4. 后端设计

### 4.1 新数据模型

`app/models/user.py` — `users` 表
| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| id | int PK | |
| email | str(255) unique index | 登录名，存小写归一 |
| name | str(100) | 显示名 |
| password_hash | str(255) | passlib bcrypt |
| is_active | bool default True | 软停用 / 席位释放 |
| last_login_at | datetime null | 最后登录（冗余，省聚合） |
| created_at | datetime server_default now | |

`app/models/login_event.py` — `login_events` 表
| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| id | int PK | |
| user_id | int FK users.id index | |
| email | str(255) | 冗余，便于展示与用户被删后留痕 |
| ip | str(64) null | 取自请求（X-Forwarded-For 优先，回落 client.host） |
| created_at | datetime server_default now | = 登录时刻 |

> **不在 `users` 存 role 字段**（见 D4）：管理员身份由 `ADMIN_EMAILS` 实时判定。
> 两张表都登记到 `app/models/__init__.py`，使 `Base.metadata` / `init_db` 能自动建表（dev）。

### 4.2 操作记录（复用两张批次表，合并读出）

实际有**两张**已存在的操作表，活路分布如下（实测确认）：

| 表 | 写入路径 | 操作人字段 | 时间字段 |
| ---- | ---- | ---- | ---- |
| `import_batches` | 文件导入 activate（`rate_batches.py` → `activator.activate`）、做表入库（`sheet_builder/db_writer.commit_*_rows`） | `imported_by`（str，可空） | `imported_at` |
| `upload_logs` | `/ai/confirm`（`ai_parse.py` → `import_parsed_rates`） | `uploaded_by`（str，可空） | `created_at` |

- **不新建操作表**。`GET /admin/operations` **合并读** `import_batches` + `upload_logs`，归一为统一行：
  `{operator, time, source(import|ai_confirm), file, file_type, status, row_count, parsed/imported}`，时间倒序、分页、可按 operator 筛。
- **盖章（写真实操作人），本期只接两条最浅且高价值的活路，且用 `get_optional_user`（非破坏）**：
  1. `/ai/confirm`：端点挂 `get_optional_user`，`import_parsed_rates(..., operator_email=user.email if user else None)` → 填 `uploaded_by`。
  2. 文件 activate：`activate_rate_batch` 端点挂 `get_optional_user`，把 `user.email`（或 None）传入 `activator.activate(...)`，替换现在硬编码的 `imported_by="step1_activator"`（无 token 时回落该默认值）。
- **做表入库（`db_writer.commit_*_rows`）盖章留作后续**：其 `imported_by` 参数已存在但调用链更深；本期**不**改这条线。它的批次**仍会出现在操作记录里**，只是 `operator` 可能不是真人（保持现状值）。这是有意的范围边界，避免深层穿线。

### 4.3 认证基建

`app/core/security.py`（新建）
- 密码：`passlib` `CryptContext(schemes=["bcrypt"])` → `hash_password()` / `verify_password()`。
- JWT：HS256；`create_access_token(sub=user_id, exp)` / `decode_access_token()`。
- 库选型：`passlib[bcrypt]` + `PyJWT`（轻、无额外依赖）。加入 `backend/requirements.txt`。

`app/core/config.py`（扩展，pydantic-settings）
- `JWT_SECRET: str`（生产必填，不入 git；dev 给占位默认并在文档标注）
- `JWT_ALGORITHM: str = "HS256"`
- `JWT_EXPIRE_MINUTES: int = 720`（12h）
- `ADMIN_EMAILS: str = ""` → 解析为小写邮箱集合（逗号分隔），提供 `is_admin_email(email)` 辅助
- `REGISTRATION_MODE: str = "open"`（`open` | `admin_only`，见 D7）

`app/api/deps.py`（扩展）
- `get_current_user(token, db)`：解 JWT → 查 `users` → 不存在/`is_active=False`/token 失效 → 401。**硬鉴权**，用于 `/auth/me` 与 `/admin/*`。
- `get_current_admin(user=Depends(get_current_user))`：`is_admin_email(user.email)` 为假 → 403。
- `get_optional_user(token, db) -> User | None`：**不抛 401**——有合法 token 返回用户，无/失效 token 返回 `None`。用于给现有业务端点盖章而**不破坏**其既有（无 token）调用与测试。

`app/services/user_service.py`（新建，建号/认证单点收口，见 D7-2）
- `create_user(db, email, password, name) -> User`：归一邮箱、去重（已存在→409/ValueError）、哈希、落库。
- `authenticate(db, email, password) -> User | None`：查用户 + 校验密码 + `is_active`。
- `record_login(db, user, ip)`：更新 `last_login_at` + 插入 `login_event`。

### 4.4 API 端点

`app/api/v1/auth.py`（新建，prefix `/auth`，挂到 `router.py`）
| 方法 | 路径 | 鉴权 | 说明 |
| ---- | ---- | ---- | ---- |
| POST | `/auth/register` | 无 | **受 `REGISTRATION_MODE` 控制**：`open`→建号并返回 token；`admin_only`→403 |
| POST | `/auth/login` | 无 | 校验→`record_login`→返回 `{token, user:{email,name,is_admin}}` |
| GET | `/auth/me` | get_current_user | 还原会话，返回当前用户 + `is_admin` |

> 登出无需后端端点（JWT 无状态，前端丢 token 即可）。

`app/api/v1/admin_activity.py`（新建，prefix `/admin`，全挂 `get_current_admin`）
| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| GET | `/admin/users` | 用户列表：email/name/is_admin/last_login_at/created_at/is_active + 汇总（活跃数/总数，见 D7-3） |
| GET | `/admin/login-events` | 登录历史，分页（limit/offset），可选 `user_id` 筛选，时间倒序 |
| GET | `/admin/operations` | 操作记录（合并 `import_batches`+`upload_logs`），分页，可选 operator 筛选，时间倒序 |

> 现有 `admin.py`（清空数据）与 `admin_settings.py` 保持不动；活动日志独立成 `admin_activity.py`，职责单一。
> 统一走现有 `ApiResponse[...]` 包装与 RESTful 错误响应。

### 4.5 数据库迁移

- 新增 alembic 迁移：建 `users` + `login_events` 两表（生产走 alembic）。
- dev 环境 `init_db()` 的 `create_all` 会自动建表，但仍补迁移以与生产一致（遵循 CLAUDE.md / DEPLOYMENT.md）。

## 5. 前端设计

- **`contexts/AuthContext.tsx` 重写**：localStorage 假账号 → 真接口。
  - `login` → `POST /auth/login`，token 存 `localStorage('hhrh_token')`，user 状态含 `isAdmin`。
  - `register` → `POST /auth/register`（拿到 token 即登录态）。
  - `logout` → 清 token。
  - 挂载时若有 token → `GET /auth/me` 还原并校验；失败则清 token。
  - `AuthUser` 增 `isAdmin: boolean`。
- **`services/api.ts`（axios）拦截器**：请求注入 `Authorization: Bearer <token>`；响应 401 → 清 token + 跳 `/login`。
- **`components/AdminRoute.tsx`（新建）**：非管理员重定向回 `/`；新路由 `/activity` 挂其下。
- **`pages/ActivityLog.tsx`（新建）**：AntD `Tabs` 三段——
  1. 用户列表（邮箱/姓名/是否管理员/最后登录/注册时间/状态 + 顶部活跃数·总数）
  2. 登录历史（用户/时间/IP，可按用户筛，分页）
  3. 操作记录（用户/时间/文件/类型/状态/解析数/入库数，分页）
- **`components/Layout`**：「活动日志」菜单项**仅 `user.isAdmin` 时渲染**。
- **`pages/Register.tsx`**：本期 `REGISTRATION_MODE` 固定 `open`，注册入口照常显示、不改动。未来切 `admin_only` 时隐藏注册入口属 §9 增量（届时前端按后端开关渲染），本期不预埋前端开关。
- **i18n**：新页面 + 登录相关新文案补齐 `zh / ja / en` 三份（缺一视为 bug）。

## 6. 数据流（登录 → 看日志）

1. 用户在 Login 页提交 → `POST /auth/login` → 后端校验、`record_login`（更新 last_login + 写 login_event）、返回 JWT。
2. 前端存 token，后续请求经 axios 拦截器带 `Authorization`。
3. 管理员（邮箱在 `ADMIN_EMAILS`）登录后，Layout 显示「活动日志」菜单。
4. 进 `/activity` → 三个 `GET /admin/*` 拉数据；非管理员即便手敲 URL 也被 `AdminRoute`（前端）+ `get_current_admin`（后端 403）双重拦下。
5. 用户上传运价文件 → 写 UploadLog 时带上 `uploaded_by=email` → 出现在「操作记录」。

## 7. 错误处理

- 注册：邮箱重复 409 / 格式或密码长度不合规 400 / `admin_only` 模式 403。
- 登录：账号不存在或密码错 401（统一文案，不区分以防枚举）；账号停用 403。
- token 缺失/失效/过期：受保护端点 401；前端拦截器清 token 跳登录。
- 越权：非管理员访问 `/admin/*` → 403。
- API 错误信息英文（遵循 CLAUDE.md「API 文档英文」），前端按需映射三语展示文案。

## 8. 测试策略

后端 pytest（沿用 `tests/conftest.py` 既有 fixture / `tests/api_v1/` 结构）：
- 注册成功建用户；重复邮箱被拒；**密码不以明文落库**（断言 `password_hash != 明文` 且能 verify）。
- `REGISTRATION_MODE=admin_only` 时 `/auth/register` 返回 403。
- 登录：错密码 401；正确 → 返回 token + `last_login_at` 被更新 + 新增一条 `login_event`；停用账号 403。
- `get_current_user`：有效 / 无效 / 过期 token 三种。
- 管理员端点：非管理员 403、管理员（邮箱 ∈ `ADMIN_EMAILS`）200；`/admin/operations` 能合并读到 `import_batches` + `upload_logs` 两表数据。
- 盖章：`/ai/confirm` 带登录用户后 `upload_logs.uploaded_by` 被填；文件 activate 带登录用户后 `import_batches.imported_by` = 该用户邮箱（非 `step1_activator`）。

前端：无测试框架，靠 `npm run build` + `npm run lint` 通过。

## 9. 后续增量（本期不做，但缝已留好 —— 对应 D7）

切「管理员指定注册 / 按人头收费」时，预计改动：
1. 配置 `REGISTRATION_MODE=admin_only`（注册端点自动 403）。
2. 新增 `POST /admin/users`（管理员建号）+ `PATCH /admin/users/{id}`（停用/启用），**复用** `user_service.create_user()`。
3. 活动日志「用户列表」加「新建用户 / 停用」操作按钮（复用现有页面）。
4. 可选：席位上限校验（建号时比对 `count(is_active=True)` 与计费档位）、邀请码 / 邮箱域名白名单。
5. 做表入库（`db_writer.commit_*_rows`）盖章真实操作人（穿线 `imported_by`），让做表批次的 operator 也是真人。

均为增量，不触及本期认证内核与数据模型。

## 10. 风险与兼容

1. **开放注册风险**（D2）：外网可达即可被任意注册；缓解手段（邀请码 / 域名白名单 / 切 admin_only）见 §9，本期不做。
2. **`JWT_SECRET` 生产必填**，不入 git；dev 占位默认须在 `.env.example` / 文档标注。
3. **现有浏览器 localStorage 演示账号作废**：上线后所有人需对后端重新注册一次（首次访问 `/auth/me` 失败 → 强制登录）。
4. 新增依赖 `passlib[bcrypt]` + `PyJWT` 需进 `requirements.txt` 并在各环境 `pip install`。
5. **后端鉴权范围边界（重要）**：本期后端**只硬性鉴权 `/auth/me` 与 `/admin/*`**；其余业务端点（rates / upload / pkg 等）**暂不在后端强制 token**，由前端 `ProtectedRoute` 把关。这与现状（全开放）相比不降级、只增强（多了真实登录与管理员可见性），但「全后端端点强制鉴权」是后续 sweep（会触及大量现有测试），不在本期。盖章用 `get_optional_user` 正是为此——不破坏现有无 token 调用。

## 11. 工时估算

约 **2~4 天**：后端（认证基建 + 两表 + 端点 + 迁移）≈ 1.5~2 天；前端（AuthContext 重写 + axios 拦截 + AdminRoute + 活动日志页 + 三语）≈ 1~1.5 天；测试贯穿其中。
