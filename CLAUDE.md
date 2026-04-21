# 阪急阪神 — 入札業務効率化プロジェクト

## 项目概述

为阪急阪神（Hankyu Hanshin，日本货运代理公司）开发 AI 驱动的招标（入札）业务自动化系统。
核心目标：将全人工投标流程自动化，从数小时/天缩短到分钟级。

## 核心业务流程

```
客户发送投标包(PKG) → AI 解析 PKG 结构 → AI 从费率库检索航线费率
→ AI 自动填入 PKG → 通知营业人员审核 → 提交投标
```

## 技术栈

- **后端**: Python + FastAPI + Celery（异步任务）
- **前端**: React + i18n（中日英三语）
- **数据库**: PostgreSQL（核心费率数据）+ Redis（可选，热门航线缓存）
- **AI**: Claude API + RAG（向量检索费率数据，防止幻觉）
- **文档处理**: pandas + openpyxl（Excel 读写）
- **部署**: Docker 容器化

## 项目结构

```
阪急阪神/
├── CLAUDE.md                          # 项目指令（本文件）
├── 项目需求分析文档.md                  # 完整需求文档
├── 入札業務の効率化(中文).pptx          # 客户原始 PPT
├── 阪急阪神_业务流程图.drawio           # 业务流程图
├── workspace/                         # PPT 解包工作区
├── backend/                           # FastAPI 后端
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口
│   │   ├── models/                    # SQLAlchemy 数据模型
│   │   ├── api/                       # API 路由
│   │   ├── services/                  # 业务逻辑
│   │   ├── skills/                    # AI Skills（parse_pkg, query_rate, fill_pkg 等）
│   │   └── core/                      # 配置、数据库连接
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                          # React 前端
│   ├── src/
│   │   ├── components/                # UI 组件
│   │   ├── pages/                     # 页面
│   │   ├── i18n/                      # 多语言文件（zh/ja/en）
│   │   └── services/                  # API 调用
│   └── package.json
├── data/                              # 费率数据与模板
│   ├── tariffs/                       # 费率表（Excel/CSV）
│   └── templates/                     # 投标包模板
├── scripts/                           # 工具脚本（数据导入等）
└── docker-compose.yml
```

## AI Skills 定义

| 技能 | 功能 |
|------|------|
| `parse_pkg` | 解析客户投标包（Excel/PDF），识别表格结构和需填字段 |
| `query_rate` | 按航线查询最新费率（起运地、目的地、服务类型、航司） |
| `fill_pkg` | 将费率数据自动填入投标包对应栏位 |
| `read_excel` | 读取 Excel 费率表 / Tariff 数据 |
| `write_excel` | 生成或更新 Excel 文件 |
| `translate` | 中日英三语互译（物流专业术语） |
| `validate_rate` | 校验费率合理性（与历史数据比对，防异常值） |
| `notify` | 填写完成后通知营业人员审核 |

## 开发规范

### 代码风格
- Python: 遵循 PEP 8，使用 type hints
- React: 函数组件 + Hooks，TypeScript
- API: RESTful 风格，统一错误响应格式
- 变量/函数命名: Python 用 snake_case，React 用 camelCase

### 多语言
- 项目涉及中文、日文、英文三语
- 代码注释和 commit message 用中文
- API 文档用英文
- 前端 UI 支持三语切换（i18n）

### 数据安全
- 费率数据属于商业敏感信息，严禁硬编码
- API Key 等敏感信息通过环境变量管理（.env，不提交 git）
- 数据库连接信息不写入代码

### 关键业务术语

| 日文 | 中文 | 英文 |
|------|------|------|
| 入札 | 招标/投标 | Bidding/Tender |
| 見積 | 报价 | Quotation |
| 費率表 | 费率表 | Tariff |
| 航線 | 航线 | Lane |
| 投標包 | 投标包 | PKG (Package) |
| 現地法人 | 当地子公司 | Local Subsidiary |
| 代理店 | 代理商 | Agent |
| 混載業者 | 联运商 | Co-loader |
| 営業 | 销售/业务 | Sales |

## 开发阶段

- **Phase 1（第1~2周）**: 数据基础建设 — 数据库建模、费率导入、FastAPI CRUD、React 管理页面
- **Phase 2（第3~5周）**: AI 核心功能 — Skills 开发、RAG 管道、PKG 解析与自动填写
- **Phase 3（第6~8周）**: 扩展功能 — 自动报价、会议纪要、知识库、多语言翻译
- **Phase 4（第9~10周）**: 上线推广 — 试运行、模板适配、Docker 部署、操作手册

## 常用命令

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install
npm run dev

# 数据库
docker-compose up -d postgres

# 测试
cd backend && pytest
cd frontend && npm test
```
