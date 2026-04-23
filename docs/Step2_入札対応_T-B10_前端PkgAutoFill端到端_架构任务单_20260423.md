# Step2 入札対応 — T-B10 前端 PkgAutoFill 端到端 架构任务单（v0.1）

- **版本**：v0.1（对应业务需求 v0.1，2026-04-23）
- **作者**：架构大师
- **业务依据**：`docs/Step2_入札対応_T-B10_前端PkgAutoFill端到端_业务需求_20260423.md`（389 行）
- **监工已拍板 Q-T-B10**：
  - Q-01：加价系数 = 1.15（T-B7 代码一致）；Demo 话术同步改 "+15%"
  - Q-02：识别卡片用 `IdentifierResult.confidence`（enum: high/medium/low + 色码）；行级表格 **不展示** `PerRowReport.confidence` 列（v0.1 简化）
  - Q-03：Customer B 拒绝日文文案 = `現バージョンは Customer A のみ対応`
- **读者**：开发大师（按本单动手）、测试大师（产出 V1-V7 清单）、监工（审计 file:line）

---

## 1. 任务定位与依赖

### 1.1 前后任务

- **依赖已完成**：
  - T-B3 `Step1RateRepository`（`backend/app/services/step2_bidding/rate_repository.py:29-110`）
  - T-B4 `CustomerAProfile.parse`（`backend/app/services/step2_bidding/customer_profiles/customer_a.py:325-361`）
  - T-B5 `RateMatcher`（`backend/app/services/step2_bidding/rate_matcher.py:32-131`，`match()` 返回 `tuple[RowStatus, list[QuoteCandidate]]`）
  - T-B7 `CustomerAProfile.fill`（同上 `:150-230`）+ `default_markup_fn`（`:612-614`，硬编码 1.15）
  - T-B8 `identify()`（`backend/app/services/step2_bidding/customer_identifier.py:44-128`）
- **依赖已推迟**（v0.1 禁止使用）：
  - T-B2 持久化两表 `bidding_requests / bidding_row_reports` —— 见 `backend/app/services/step2_bidding/TODO_T_B2.md`，v0.1 不落库
  - T-B6 `Markup/Validator` 管道 —— v0.1 用 `default_markup_fn` 兜底
  - T-B9 service.py 5 步编排 + 状态机 —— v0.1 编排直接写在 endpoint / 一个新的轻量 orchestrator 函数里，不引入 `BiddingStatus` 状态机
- **后续任务**：
  - T-B10 v0.2：等 T-B2 / T-B9 齐活后补持久化 + 审核改价 + 5 个剩余 endpoint（列表/单查/PATCH/submit/candidates）
  - T-B11：删旧 `pkg_parser.py / pkg_filler.py` 及 `/api/v1/pkg.py`；本轮保留共存
  - T-B12：pytest 验收全集

### 1.2 范围边界（对应业务需求 §1）

- **只做 2 个 endpoint**：`POST /api/v1/bidding/auto-fill`（一次性自动填入）+ `GET /api/v1/bidding/download/{token}`（一次性 token 下载）
- **沿用前端路由 `/pkg`**（`frontend/src/App.tsx:57`），不新增路由
- **`pages/PkgAutoFill.tsx` 整页重写**（526 行 → 约 400 行新版），旧 `pkgApi` 保留（T-B11 删），不复用
- **v0.1 不引入 Playwright**（业务需求 §9 只要求手工浏览器验收）

---

## 2. 文件级改动清单

### 2.1 后端新增

| 路径 | 作用 | 估算行数 |
|---|---|---|
| `backend/app/api/v1/bidding.py` | FastAPI 路由：`POST /bidding/auto-fill`、`GET /bidding/download/{token}` | ~140 |
| `backend/app/schemas/bidding.py` | Pydantic Schema：`BiddingAutoFillResponse` + 4 个子 DTO + 错误码枚举 | ~180 |
| `backend/app/services/step2_bidding/bidding_orchestrator.py` | 同步编排函数 `run_auto_fill()`：identify → parse → match → fill×2；全异常归口 F1-F4 | ~180 |
| `backend/app/services/step2_bidding/token_store.py` | 进程级内存 TokenStore（`put / consume / sweep`），一次性 + 1 小时 TTL | ~90 |
| `backend/app/services/step2_bidding/temp_files.py` | 临时目录管理 `alloc_bid_dir(bid_id) / cleanup_expired()`；基于 mtime 的 lazy sweep | ~60 |

### 2.2 后端修改

| 路径 | 改动 | 行区间 |
|---|---|---|
| `backend/app/api/v1/router.py` | 新增 `from app.api.v1.bidding import router as bidding_router` + `router.include_router(bidding_router)` | 追加在 `:12` 和 `:23` 之后（共 2 行新增） |
| `backend/app/services/step2_bidding/__init__.py` | 导出 `run_auto_fill`（可选；便于 pytest 直接调用） | 追加 1 行 import + `__all__` 末尾 1 行 |

### 2.3 前端新增

| 路径 | 作用 | 估算行数 |
|---|---|---|
| `frontend/src/types/bidding.ts` | TypeScript 类型定义（对应后端 Schema，含 enum / status / dto） | ~120 |

### 2.4 前端修改

| 路径 | 改动 | 行区间 |
|---|---|---|
| `frontend/src/pages/PkgAutoFill.tsx` | 整页重写：删除 sessionId / parse / fill 两段调用，改为单次 `biddingApi.autoFill()`；重构状态机 + 5 个面板 | `:1-526` 全替换 |
| `frontend/src/services/api.ts` | 新增 `biddingApi = { autoFill(file), downloadUrl(token) }` | 追加在 `:194` 末尾 |
| `frontend/src/i18n/zh.json` | 新增 `bidding.*` namespace（6 组约 60 个 key） | 追加在 `:408` 后（与 `pkg` 同级） |
| `frontend/src/i18n/ja.json` | 同 zh | 对应 `:357` 附近同位置 |
| `frontend/src/i18n/en.json` | 同 zh | 同上 |

**不动的**：`pkg` namespace 里已有的 key、`/api/v1/pkg.py`、旧 `pkgApi`、旧 `pkg_parser.py / pkg_filler.py`。保留共存给 T-B11 删。

---

## 3. 接口契约

### 3.1 `POST /api/v1/bidding/auto-fill`

**请求**：`multipart/form-data`，单字段 `file`（UploadFile，xlsx）。无其他参数。

**成功响应**：`200 OK`，`application/json`，body schema = `BiddingAutoFillResponse`：

```python
class BiddingErrorCode(str, Enum):
    F1_INVALID_XLSX = "F1_INVALID_XLSX"
    F2_UNSUPPORTED_CUSTOMER = "F2_UNSUPPORTED_CUSTOMER"
    F3_PARSE_FAILED = "F3_PARSE_FAILED"
    F4_FILL_FAILED = "F4_FILL_FAILED"
    F5_TOKEN_EXPIRED = "F5_TOKEN_EXPIRED"
    F6_FILE_TOO_LARGE = "F6_FILE_TOO_LARGE"
    F7_WRONG_EXTENSION = "F7_WRONG_EXTENSION"
    F8_NETWORK_ERROR = "F8_NETWORK_ERROR"  # 前端兜底，不从后端产

class IdentifyBlock(BaseModel):
    matched_customer: Literal["customer_a", "unknown"]
    matched_dimensions: list[str]          # 例 ["B", "D"]
    confidence: Literal["high", "medium", "low"]
    unmatched_reason: str | None
    warnings: list[str]

class ParseBlock(BaseModel):
    period: str
    sheet_name: str
    section_count: int
    row_count: int
    sample_rows: list["SampleRow"]          # 至多 5
    warnings: list[str]

class SampleRow(BaseModel):
    row_idx: int
    section_code: str
    destination_text: str                   # 用 PkgRow.destination_text_raw
    cost_type: Literal["air_freight", "local_delivery", "unknown"]

class FillRowBlock(BaseModel):
    row_idx: int
    section_code: str
    destination_code: str
    status: str                              # RowStatus.value 8 种
    cost_price: str | None                   # Decimal → str
    sell_price: str | None                   # cost 版为 None；sr 版 = markup(cost)
    markup_ratio: str | None                 # "1.15"；从 default_markup_fn 推断或 FillReport 字段
    source_batch_id: str | None              # QuoteCandidate.source_batch_id

class FillBlock(BaseModel):
    filled_count: int
    no_rate_count: int
    skipped_count: int
    global_warnings: list[str]
    rows: list[FillRowBlock]                 # 全量（不摘要；21 行 Demo 可接受）
    markup_ratio: str                        # "1.15" —— Demo 提示条用这个值，不在前端硬编码

class DownloadTokens(BaseModel):
    cost_token: str
    sr_token: str
    cost_filename: str                        # "cost_<basename>_<bid_id>.xlsx"
    sr_filename: str                          # "sr_<basename>_<bid_id>.xlsx"
    expires_at: datetime                      # UTC
    one_time_use: bool = True

class BiddingAutoFillResponse(BaseModel):
    bid_id: str                               # "yyyymmdd_HHMMSS_<uuid4[:8]>"
    ok: bool                                  # True 只要 identify 拿到 customer_a 且 parse/fill 都成功
    error: BiddingErrorBlock | None           # ok=False 时必填
    identify: IdentifyBlock
    parse: ParseBlock | None                  # unknown / parse_failed 时为 None
    fill: FillBlock | None                    # unknown / parse_failed / fill_failed 时为 None
    download: DownloadTokens | None           # 同上

class BiddingErrorBlock(BaseModel):
    code: BiddingErrorCode
    message_key: str                           # 前端 i18n key 如 "bidding.errors.f2_unsupported_customer"
    detail: str                                # 供浏览器 console / 后续排障用，不直接显示
```

**降级策略（响应体保持 200）**：

| 后端分支 | ok | identify | parse | fill | download | error.code |
|---|---|---|---|---|---|---|
| F1 xlsx 打不开 | False | identify.warnings 含 `WBOPEN_FAIL: ...` | None | None | None | F1 |
| F2 unknown | False | 完整 | None | None | None | F2 |
| F3 parse 抛异常 | False | 完整 (customer_a) | None | None | None | F3 |
| F4 fill 抛异常 / match 全 0 行 | False | 完整 | 完整 | None | None | F4 |
| 正常 customer_a | True | 完整 | 完整 | 完整 | 完整 | None |

> **F2/F3/F4 不走 HTTP 4xx/5xx**：业务需求 §4.1 最末段要求"降级返回"，前端好根据分支渲染各面板。

**非降级 HTTP 错误**：

| HTTP | 场景 | 响应体 |
|---|---|---|
| 400 | 扩展名非 xlsx / 空 file 字段（前端已拦截，服务端二次守门） | `{detail: "F7_WRONG_EXTENSION: ..."}` |
| 413 | 文件 > 10 MB | `{detail: "F6_FILE_TOO_LARGE: ..."}` |
| 500 | 编排器未捕获的异常（不应发生） | FastAPI 默认 |

### 3.2 `GET /api/v1/bidding/download/{token}`

**请求**：path param `token` (string)。

**响应**：
- `200 OK`：`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`，`Content-Disposition: attachment; filename="<filename>"`，body = xlsx 二进制。
- `410 Gone`：token 不存在 / 过期 / 已用。响应体：`{"detail": "F5_TOKEN_EXPIRED: ..."}`。

**一次性实现**：`token_store.consume(token)` 先原子 pop（拿到 path），返回 FileResponse；拿不到就 410。`consume` 内部用 `threading.Lock` 保护 dict（避免多 worker 并发重复下载——虽然 uvicorn 单 worker Demo 场景冲突概率低，但显式加锁 10 行代码成本低）。

### 3.3 错误码 ↔ 业务需求 §6 F1-F8 映射表

| 代号 | 触发 | HTTP | 后端位置 | 前端文案 i18n key |
|---|---|---|---|---|
| F1 | `identify()` 返回含 `WBOPEN_FAIL` warning 的 unknown | 200（降级）| `bidding_orchestrator.run_auto_fill`：identify 分支 | `bidding.errors.f1_invalid_xlsx` |
| F2 | identify 返回 `matched_customer == "unknown"` 且无 F1 warning | 200（降级）| 同上 | `bidding.errors.f2_unsupported_customer`（不直接显示 error.message_key，由 §5.1 状态 4 红色警告区显示）|
| F3 | `profile.parse()` 抛异常 | 200（降级）| orchestrator try/except 包 parse | `bidding.errors.f3_parse_failed` |
| F4 | `matcher.match()` 全部 row 0 候选 / `profile.fill()` 抛异常 | 200（降级）| orchestrator try/except 包 match+fill | `bidding.errors.f4_fill_failed` |
| F5 | token 不存在 / 过期（>1h）/ 已下载过 | 410 | `bidding.py download` endpoint | `bidding.errors.f5_token_expired` |
| F6 | Content-Length > 10 MB | 413 | `bidding.py auto-fill` endpoint（读 body 前） | `bidding.errors.f6_file_too_large` |
| F7 | `file.filename` 扩展名 ∉ `{.xlsx}` | 400 | 同上 | `bidding.errors.f7_wrong_extension` |
| F8 | fetch 异常 / 网络中断 | - | **前端 axios interceptor 捕获** | `bidding.errors.f8_network_error` |

**业务需求 §6 最末段硬要求**：后端异常 `detail` 字段可带 exception summary（前端 console 排障），但 UI 显示永远用 `message_key` 对应的 i18n 文案，**不透出 traceback**。

---

## 4. 数据流（7 步序列）

```
[用户] -- 拖拽 2-①.xlsx --▶ [PkgAutoFill.tsx]
     (1) 本地校验：扩展名 in {.xlsx}，size ≤ 10MB；失败 → F7/F6 文案，不发请求

[PkgAutoFill.tsx] -- POST /api/v1/bidding/auto-fill (multipart) --▶ [bidding.py]
     (2) FastAPI 端点：
         - Content-Length 校验 → F6
         - 扩展名二次校验 → F7
         - 生成 bid_id = f"{yyyymmdd_HHMMSS}_{uuid4().hex[:8]}"
         - temp_files.alloc_bid_dir(bid_id) → /tmp/hankyu_bidding/<bid_id>/
         - 把 UploadFile 落到 input.xlsx
         - 调 bidding_orchestrator.run_auto_fill(input_path, bid_id, db_session)

[bidding_orchestrator.run_auto_fill] 内部：
     (3) identify(input_path) → IdentifierResult
         ├── matched_customer == "unknown"
         │   ├── 含 WBOPEN_FAIL warning → code=F1, return 降级响应 (仅 identify)
         │   └── 其他 unknown        → code=F2, return 降级响应 (仅 identify)
         └── customer_a → 继续

     (4) profile.parse(input_path, bid_id, period="") → ParsedPkg
         try/except 全部异常 → code=F3, return 降级响应 (identify + 无 parse)

     (5) For row in parsed.rows: RateMatcher.match(row, effective_on=today)
         → per_row_reports: list[PerRowReport]
         - effective_on 用业务日期：T-B5 v0.1 取 datetime.utcnow().date()（加 FIXME 注释：T-B10 v0.2 由 parsed.period 推导）
         - 每个 row 产一个 PerRowReport（见 §5.2 映射规则）
         - 全部行 status=NO_RATE 且 section_code=="PVG" 时计为 F4（match 0 行）触发？→ NO，保持 fill 流程继续（业务需求 §6 F4 场景仅捕获 fill 抛异常，no_rate=5 属于 V6 场景，不是 F4）

     (6) profile.fill(variant="cost", output=/tmp/.../cost.xlsx) → FillReport_cost
         profile.fill(variant="sr",   output=/tmp/.../sr.xlsx)   → FillReport_sr
         try/except 全部异常 → code=F4, return 降级响应 (identify + parse)

     (7) token_store.put(uuid4().hex, path=cost.xlsx, filename="cost_<basename>_<bid_id>.xlsx", ttl=3600)
         token_store.put(...) for sr
         → 组装 BiddingAutoFillResponse，ok=True，返回

[PkgAutoFill.tsx] 收到响应 → 根据 ok + error.code 切换状态：
     - ok=True → 状态 3（完成）：渲染 4 个面板 + 2 个下载按钮
     - error.code in {F1, F3, F4} → 状态 5（失败）：红色 Alert + 文案
     - error.code = F2 → 状态 4（拒绝）：红/橙 Alert + unmatched_reason

[用户点"下载 cost"] -- GET /bidding/download/<cost_token> --▶ [bidding.py]
     token_store.consume(token) → path; 返回 FileResponse；token 从 dict pop
     浏览器触发"另存为"，默认 filename 来自 Content-Disposition
```

**lazy sweep 点**：每次 `token_store.put` 前调一次 `sweep_expired()`；再加 `bidding_orchestrator.run_auto_fill` 开头调一次 `temp_files.cleanup_expired(ttl=3600)`。**不引入 APScheduler / 后台线程**（uvicorn --reload 下后台线程易泄漏，且 Demo 单会话跑完即删更干净）。

---

## 5. 算法 / 编排分支

### 5.1 `run_auto_fill` 伪代码

```python
def run_auto_fill(
    input_path: Path,
    bid_id: str,
    bid_dir: Path,
    db: Session,
) -> BiddingAutoFillResponse:
    temp_files.cleanup_expired(ttl=3600)

    identify_result = identify(input_path)
    identify_block = _to_identify_block(identify_result)

    if identify_result.matched_customer == "unknown":
        code = _classify_unknown(identify_result.warnings)  # F1 or F2
        return _resp_error(bid_id, identify_block, code)

    profile = CustomerAProfile(markup_fn=default_markup_fn)

    try:
        parsed = profile.parse(input_path, bid_id=bid_id, period="")
    except Exception as e:
        return _resp_error(bid_id, identify_block, F3, detail=repr(e))

    parse_block = _to_parse_block(parsed, sample_limit=5)

    try:
        repo = Step1RateRepository(db)
        matcher = RateMatcher(repo)
        effective_on = datetime.utcnow().date()  # FIXME v0.2: 从 parsed.period 推导
        row_reports = _match_all_rows(parsed, matcher, effective_on)

        cost_path = bid_dir / f"cost_{input_path.stem}_{bid_id}.xlsx"
        sr_path   = bid_dir / f"sr_{input_path.stem}_{bid_id}.xlsx"
        fr_cost = profile.fill(input_path, parsed, row_reports, "cost", cost_path)
        fr_sr   = profile.fill(input_path, parsed, row_reports, "sr",   sr_path)
    except Exception as e:
        return _resp_error(bid_id, identify_block, F4, parse_block=parse_block, detail=repr(e))

    # 成功路径
    fill_block = _to_fill_block(
        fr_cost=fr_cost, fr_sr=fr_sr, row_reports=row_reports,
        markup_ratio=Decimal("1.15"),
    )
    cost_token = token_store.put(cost_path, cost_path.name, ttl=3600)
    sr_token   = token_store.put(sr_path,   sr_path.name,   ttl=3600)

    return BiddingAutoFillResponse(
        bid_id=bid_id, ok=True, error=None,
        identify=identify_block, parse=parse_block, fill=fill_block,
        download=DownloadTokens(cost_token=..., sr_token=..., ...),
    )
```

### 5.2 `_match_all_rows` 每行产 `PerRowReport` 的映射（关键！）

`RateMatcher.match()` 返回 `(RowStatus, list[QuoteCandidate])`。`PerRowReport` 构造规则：

```python
def _row_report_from_match(row: PkgRow, status: RowStatus, cands: list[QuoteCandidate]) -> PerRowReport:
    if status == RowStatus.FILLED and cands:
        top = cands[0]  # matcher 已按 cost_price 升序
        return PerRowReport(
            row_idx=row.row_idx,
            section_code=row.section_code,
            destination_code=row.destination_code,
            status=RowStatus.FILLED,
            cost_price=top.cost_price,
            sell_price=default_markup_fn(top.cost_price),  # T-B7 fill 走一样的函数，这里复算供前端显示
            markup_ratio=Decimal("1.15"),
            lead_time_text=f"{top.base_price_day_index}天" if top.base_price_day_index else None,  # FIXME v0.2: 让 matcher 回填真实 lead_time_text
            carrier_text=top.service_desc or (top.airline_codes[0] if top.airline_codes else None),
            remark_text=top.remarks_from_step1,
            selected_candidate=top,
            confidence=top.match_score,
        )
    # 非 FILLED 分支：cost/sell/carrier 均为 None
    return PerRowReport(
        row_idx=row.row_idx,
        section_code=row.section_code,
        destination_code=row.destination_code,
        status=status,
        cost_price=None, sell_price=None, markup_ratio=None,
        lead_time_text=None, carrier_text=None,
        remark_text=None, selected_candidate=None, confidence=0.0,
    )
```

> **架构留档**：`PerRowReport.lead_time_text / carrier_text` 当前从 `QuoteCandidate` 简单投影。T-B6 交付后由 Validator 管道产，届时改此函数即可；本轮 3 行简单代码 > 过早抽象。

### 5.3 `_classify_unknown(warnings)`

```python
def _classify_unknown(warnings: tuple[str, ...]) -> BiddingErrorCode:
    for w in warnings:
        if w.startswith("WBOPEN_FAIL"):
            return BiddingErrorCode.F1_INVALID_XLSX
    return BiddingErrorCode.F2_UNSUPPORTED_CUSTOMER
```

---

## 6. 临时文件 + Token 管理

### 6.1 目录布局

```
/tmp/hankyu_bidding/                       # 根目录（进程启动时 mkdir -p）
├── 20260424_103015_a1b2c3d4/              # bid_id
│   ├── input.xlsx                         # 原上传文件
│   ├── cost_2-①_20260424_103015_a1b2c3d4.xlsx
│   └── sr_2-①_20260424_103015_a1b2c3d4.xlsx
├── 20260424_103020_e5f6g7h8/
│   └── ...
```

> **Windows 兼容**：`/tmp` 不存在 → 用 `tempfile.gettempdir() / "hankyu_bidding"`，由 `temp_files.py` 抽象。

### 6.2 `token_store.py` 契约

```python
class _Entry(NamedTuple):
    path: Path
    filename: str
    expires_at: datetime

class TokenStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    def put(self, path: Path, filename: str, ttl: int = 3600) -> str:
        token = uuid4().hex
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        with self._lock:
            self._sweep_expired()
            self._entries[token] = _Entry(path, filename, expires_at)
        return token

    def consume(self, token: str) -> _Entry | None:
        """一次性：拿到就 pop。拿不到或已过期返回 None。"""
        with self._lock:
            entry = self._entries.pop(token, None)
        if entry is None:
            return None
        if entry.expires_at < datetime.utcnow():
            # 过期了，同时清理磁盘文件
            entry.path.unlink(missing_ok=True)
            return None
        return entry

    def _sweep_expired(self) -> None:
        """调用方已持锁。"""
        now = datetime.utcnow()
        dead = [t for t, e in self._entries.items() if e.expires_at < now]
        for t in dead:
            e = self._entries.pop(t)
            e.path.unlink(missing_ok=True)

# 模块级单例
TOKEN_STORE = TokenStore()
```

**并发安全讨论**：
- uvicorn Demo 默认单 worker、多协程。`threading.Lock` 对多线程和纯协程（sync endpoint）都够用。
- 若未来上多 worker（uvicorn --workers 4），进程间不共享 dict → 本方案失效。那时换 Redis，是 v0.2 的事。v0.1 **显式标注单进程限制**写在 `token_store.py` docstring。
- `uvicorn --reload` 热重载会重建进程 → dict 丢失 = 既有 token 全部 410。对 Demo 无影响（Demo 不会热重载）。

### 6.3 `temp_files.py` 契约

```python
ROOT = Path(tempfile.gettempdir()) / "hankyu_bidding"

def alloc_bid_dir(bid_id: str) -> Path:
    d = ROOT / bid_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def cleanup_expired(ttl: int = 3600) -> None:
    """删除所有 mtime > ttl 秒的子目录（lazy sweep）。"""
    if not ROOT.exists():
        return
    cutoff = time.time() - ttl
    for sub in ROOT.iterdir():
        if sub.is_dir() and sub.stat().st_mtime < cutoff:
            shutil.rmtree(sub, ignore_errors=True)
```

---

## 7. 子任务拆分

> 粒度：每个 0.5-1 人日。并发/顺序已标注。

| ID | 标题 | 依赖 | 粒度 | 说明 |
|---|---|---|---|---|
| T-B10a | 后端：`schemas/bidding.py` 完整定义 | - | 0.5d | 纯 Pydantic，无运行依赖 |
| T-B10b | 后端：`token_store.py` + `temp_files.py` | T-B10a | 0.5d | 独立可单测 |
| T-B10c | 后端：`bidding_orchestrator.run_auto_fill` | T-B10a, T-B10b | 1d | 真逻辑主体；包含 `_match_all_rows` / `_classify_unknown` / Schema 转换 |
| T-B10d | 后端：`api/v1/bidding.py` + `router.py` 挂载 | T-B10c | 0.5d | FastAPI endpoint 薄壳 + 扩展名 / size 守门 |
| T-B10e | 前端：`types/bidding.ts` + `services/api.ts` 扩 `biddingApi` | T-B10a（看 schema） | 0.5d | 可与 T-B10c/d 并行开工（Schema 先行） |
| T-B10f | 前端：`pages/PkgAutoFill.tsx` 整页重写 | T-B10e | 1.5d | 最大块：状态机 + 5 面板 + Dropzone 本地校验 |
| T-B10g | i18n：zh/ja/en 三文件扩 `bidding.*` namespace | T-B10f 平行 | 0.5d | 文案可由业务大师提供或从业务需求 §5.2 / §6 抄 |
| T-B10h | 人工烟测（开发自测 V1-V3 + V5） | 所有 | 0.5d | 没跑过一遍不能交给测试大师 |

**并发线**：
- T-B10a 先行
- T-B10b + T-B10c（串行）/ T-B10e + T-B10g（并行） 
- T-B10d 在 T-B10c 后
- T-B10f 最后串成

**总工期估算**：5.5 人日；开发大师单线 ≈ 一周；并发两条线 ≈ 3-4 天。

---

## 8. 测试辅助建议

### 8.1 pytest fixture（后端 API 层，交给测试大师）

```python
# tests/api/v1/conftest.py
@pytest.fixture
def client(db_session_factory) -> TestClient:
    """FastAPI TestClient + 覆盖 get_db 依赖。"""
    app.dependency_overrides[get_db] = db_session_factory
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def customer_a_xlsx() -> Path:
    """黄金样本路径。"""
    return Path("资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx")

@pytest.fixture
def customer_b_xlsx() -> Path:
    """Customer B LCL 样本（用于 F2 验收）。"""
    return Path("资料/2026.04.02/Customer B (LCL)/.../2-①.xlsx")  # 由测试大师指定

@pytest.fixture
def corrupt_xlsx(tmp_path) -> Path:
    """损坏文件：把 .txt 改名。"""
    p = tmp_path / "bad.xlsx"
    p.write_text("this is not a zip")
    return p

@pytest.fixture(autouse=True)
def _clear_token_store():
    """每个 test 用例前清空 token dict，避免串味。"""
    from app.services.step2_bidding.token_store import TOKEN_STORE
    TOKEN_STORE._entries.clear()
```

### 8.2 建议的 pytest 用例矩阵

| 用例 | 期望 |
|---|---|
| `test_auto_fill_customer_a_success` | 200 / ok=True / identify.matched_customer=customer_a / download.cost_token 非空 |
| `test_auto_fill_customer_b_rejected` | 200 / ok=False / error.code=F2 / parse=None / download=None |
| `test_auto_fill_corrupt_file` | 200 / ok=False / error.code=F1 / identify.warnings 含 WBOPEN_FAIL |
| `test_auto_fill_wrong_extension` | 400 / detail 含 F7 |
| `test_auto_fill_too_large` | 413 / detail 含 F6 |
| `test_download_once_then_expire` | 第一次 200、第二次 410 |
| `test_download_expired_ttl` | `monkeypatch.setattr(TOKEN_STORE._entries[t], "expires_at", past)` → 410 |

### 8.3 前端 E2E 手工清单（对应业务需求 §9 V1-V7）

> 本轮不引入 Playwright；测试大师产出一份 Markdown checklist，五月 Demo rehearsal 前手工走一遍。

- V1 Customer A 正向：拖 `2-①.xlsx` → 秒表计时 ≤15s → 识别卡片显示 "Customer A / high" → 填入面板显示 "5 / 0 / 16" → 加价提示条显示 "1.15" → cost/sr 两按钮可点 → 下载 cost 文件名以 `cost_` 起 → openpyxl 读 E13=45
- V2 Customer B 拒绝：拖 Customer B xlsx → 红/橙警告区显示 `現バージョンは Customer A のみ対応` → 无下载按钮 → 只有"重新上传"
- V3 损坏 xlsx：拖 `.txt` 改名 `.xlsx` → F1 文案 → 不白屏 → 不 traceback
- V4 Excel Desktop 打开（人工抽检）
- V5 三语切换：zh → ja → en 逐屏对照 §5.2 的 6 组文案
- V6 Step1 费率空：清空 `air_freight_rates` 表 → V1 重跑 → filled=0 / no_rate=5
- V7 文件限制：`.xls` / `.xlsm` / `.pdf` / 20MB xlsx 各拖一次 → 前端立即拒绝 → Network 面板无请求

---

## 9. i18n namespace 策略

**决定**：新开 `bidding.*` namespace，**不**扩 `pkg.*`。理由：
1. 业务语义变了：`bidding` = 招标业务对象；`pkg` = 旧文件自动填空管线（v0.1 共存、T-B11 删）。并存期要区分清楚，避免翻译复用错。
2. 开发大师删旧 pkg 时文案可一并删，不留死 key。

**字段清单**（对应业务需求 §5.2 六组；key 命名开发大师可微调）：

```json
"bidding": {
  "title": "...",
  "subtitle": "...",
  "upload": {
    "dragText": "...",
    "hint": "...",
    "limits": { "ext": ".xlsx only", "size": "Max 10 MB" },
    "uploading": "..."
  },
  "stepBar": { "upload": "...", "processing": "...", "done": "..." },
  "identify": {
    "title": "...",
    "confidence": { "high": "...", "medium": "...", "low": "..." },
    "dimensionsLabel": "...",
    "rejected": {
      "title": { "zh": "当前版本仅支持 Customer A", "ja": "現バージョンは Customer A のみ対応", "en": "This version only supports Customer A" },
      "reasonLabel": "..."
    }
  },
  "parse": {
    "summaryTemplate": "入札期間 {{period}} · Sheet {{sheet}} · {{sections}} 段 · {{rows}} 行",
    "warningsToggle": "...",
    "sampleRowsTitle": "..."
  },
  "fill": {
    "filled": "...", "noRate": "...", "skipped": "...",
    "markupHintTemplate": "加价系数：{{ratio}}（默认值，待楢崎确认）",
    "rowsTableTitle": "...",
    "rowStatus": {
      "filled": "...", "no_rate": "...", "already_filled": "...",
      "example": "...", "non_local_leg": "...", "local_delivery_manual": "...",
      "constraint_block": "...", "overridden": "..."
    }
  },
  "download": {
    "costBtn": "下载成本价版（社内決裁用）",
    "srBtn": "下载销售价版（客户送付用）",
    "expiresHint": "凭证 1 小时后失效 / 仅可下载一次",
    "resetBtn": "重新上传"
  },
  "errors": {
    "f1_invalid_xlsx": "...",
    "f2_unsupported_customer": "...",
    "f3_parse_failed": "解析失败：{{detail}}",
    "f4_fill_failed": "自动填入失败：{{detail}}",
    "f5_token_expired": "...",
    "f6_file_too_large": "...",
    "f7_wrong_extension": "...",
    "f8_network_error": "..."
  }
}
```

**关键点**：`fill.markupHintTemplate` 用 `{{ratio}}` 占位，前端 `t('bidding.fill.markupHintTemplate', { ratio: fillBlock.markup_ratio })`。这样 **"1.15" 完全不在前端代码里出现**，T-B6 将来如果把 default_markup_fn 改成动态值，后端返回什么前端就显示什么。

---

## 10. 前端状态机骨架

**决定**：用 `useState` + 字符串 enum，不用 `useReducer`。理由：T-B10 v0.1 状态只有 5 个、转移单向、无复杂组合；`useReducer` 会为简单场景增加认知成本（参照 CLAUDE.md "premature abstraction"）。

```tsx
type UiState =
  | { kind: "idle" }
  | { kind: "uploading"; progress: number }  // 由 axios onUploadProgress 驱动
  | { kind: "processing" }                    // 上传完成，等待后端响应
  | { kind: "success"; resp: BiddingAutoFillResponse }
  | { kind: "rejected"; resp: BiddingAutoFillResponse }  // error.code=F2
  | { kind: "error"; resp: BiddingAutoFillResponse | null; code: BiddingErrorCode };

function PkgAutoFill() {
  const [ui, setUi] = useState<UiState>({ kind: "idle" });
  const { t } = useTranslation();

  const handleFile = async (file: File) => {
    // 本地校验
    if (!file.name.toLowerCase().endsWith(".xlsx"))
      return setUi({ kind: "error", resp: null, code: "F7_WRONG_EXTENSION" });
    if (file.size > 10 * 1024 * 1024)
      return setUi({ kind: "error", resp: null, code: "F6_FILE_TOO_LARGE" });

    setUi({ kind: "uploading", progress: 0 });
    try {
      const resp = await biddingApi.autoFill(file, (p) => setUi({ kind: "uploading", progress: p }));
      setUi({ kind: "processing" });
      // 依据后端降级响应分流
      if (resp.ok) return setUi({ kind: "success", resp });
      if (resp.error?.code === "F2_UNSUPPORTED_CUSTOMER")
        return setUi({ kind: "rejected", resp });
      return setUi({ kind: "error", resp, code: resp.error!.code });
    } catch (e) {
      setUi({ kind: "error", resp: null, code: "F8_NETWORK_ERROR" });
    }
  };

  // 渲染根据 ui.kind 分流，每个 panel 独立组件
  return (
    <div className="page">
      <StepBar state={ui.kind} />
      {ui.kind === "idle" && <UploadZone onFile={handleFile} />}
      {ui.kind === "uploading" && <ProgressView progress={ui.progress} />}
      {ui.kind === "processing" && <ProcessingView />}
      {ui.kind === "success" && (
        <>
          <IdentifyPanel identify={ui.resp.identify} />
          <ParsePanel parse={ui.resp.parse!} />
          <FillPanel fill={ui.resp.fill!} />
          <DownloadPanel download={ui.resp.download!} onReset={() => setUi({ kind: "idle" })} />
        </>
      )}
      {ui.kind === "rejected" && <RejectedPanel identify={ui.resp.identify} onReset={...} />}
      {ui.kind === "error" && <ErrorPanel code={ui.code} detail={ui.resp?.error?.detail} onReset={...} />}
    </div>
  );
}
```

---

## 11. 开放问题（给监工决策）

| ID | 问题 | 建议默认 |
|---|---|---|
| Q-ARCH-T-B10-01 | `effective_on` 本轮用 `datetime.utcnow().date()`，Demo 当天应该刚好落在 Step1 周报价窗口内，但跨天 / 跨周演练需要注意。是否需要在 bidding_orchestrator 里接受可选 `effective_on` 查询参数（不暴露前端、仅 pytest 注入）？ | 是，加可选 kwarg，不走 FastAPI query；pytest 直接调函数传 |
| Q-ARCH-T-B10-02 | `FillBlock.rows` 给前端 **全量 21 行** 还是 **只给 PVG 段 5 行 + filled + no_rate**？业务需求 §5.1 状态 3 面板 3 要求"每行状态摘要表格"，未明确是否含非 PVG 的 16 行 skipped。 | 全量 21 行（含 NON_LOCAL_LEG / EXAMPLE / LOCAL_DELIVERY_MANUAL），前端默认折叠该表格，展开时显示全 21 行；Demo 讲解 PVG 5 行时也能看到"为什么其它段不填" |
| Q-ARCH-T-B10-03 | token 1 小时 TTL 若 uvicorn --reload 触发热重载会丢；是否需要在 `token_store.py` 加"启动时扫 /tmp/hankyu_bidding/ 恢复"逻辑？ | 否。Demo 不热重载；生产用 Redis 是 v0.2 的事 |
| Q-ARCH-T-B10-04 | `PerRowReport.lead_time_text` 当前从 `QuoteCandidate.base_price_day_index` 简单生成"N天"字符串。Customer A 黄金样本的 F 列原文通常是日文"2～3日"等，v0.1 的简单版本是否够看？ | 够 Demo 看（监工已说 v0.1 不追求精确）；T-B6 补 |
| Q-ARCH-T-B10-05 | 前端 `FillRowBlock.confidence` 字段（Q-02 已拍 "行级不展示"）—— Schema 里是否还保留此字段？ | 保留但前端不渲染；给 T-B10 v0.2 补行级表格时直接用，不改 Schema |

---

## 12. 自检

- [x] 每个 file:line 引用都是真实存在的（已用 Read 工具核验 10 个关键文件）。
- [x] 未引入新的过度抽象（不抽 `Orchestrator` 类、不搞通用 endpoint 工厂；`run_auto_fill` 是一个函数）。
- [x] 未违反 T-B2 留档（BiddingRequest / BiddingRowReport 只在内存流动）。
- [x] 路由沿用 `/pkg`；旧 `pkgApi` 保留共存。
- [x] 下载 token 一次性 + 1 小时 TTL 明确方案。
- [x] 1.15 从后端返回 `markup_ratio` 字段，前端 i18n 占位符渲染，不硬编码。
- [x] 每个子任务可在 0.5-1 人日内完成。
- [x] Schema 字段对应到现有 `IdentifierResult / ParsedPkg / FillReport / PerRowReport / QuoteCandidate` 的映射全部给出。

---

## 变更记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v0.1 | 2026-04-23 | 架构大师 | 首版；依据业务需求 v0.1 + Q-T-B10-01/02/03 拍板；8 个子任务；5 开放问题交监工 |
