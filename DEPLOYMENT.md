# 服务器部署清单（阪急阪神 入札業務効率化システム）

> 写给在服务器上做部署 / 升级的同事（包括 AI 助手）。
>
> **最常踩的坑：**
> 1. 只 `git pull` 没重启后端 / 没重新构建前端 → 看到的还是旧代码，新功能不生效
> 2. 重启 uvicorn 时换了 cwd，运价文件落到不可写目录 → 上传 500 / Permission denied
> 3. 没装新依赖 / 没跑 alembic 升级 → 起不来或某些接口 500
> 4. 前端 `VITE_API_BASE_URL` 没配 → 浏览器请求打到 `localhost:8000` 直接超时
> 5. 数据库被同事点过 reset 后字典没回来 → 所有运价导入全 `CARRIER_NOT_FOUND` 0 行入库
>
> **所以每次部署，下面五个区块都要一遍一遍核到位，不能跳。**

---

## 0. 部署前先看一眼最近的修复

下面这些 commit 的修复点，部署完一定要在生产复测一次，否则等同没修：

| Commit | 修了什么 | 复测办法 |
|---|---|---|
| `4dcaeee` 船司/供应商页 only_used 过滤 | 清空运价后供应商页只显字典船司；导入后只显命中船司 | 进入「船司/供应商」页，看是否随运价一起变化 |
| `489e65b` upload_dir 绝对化 + reset 语义 | uvicorn 不在 backend/ 启动也能写 `uploads/`；reset 提示文案如实 | 上传一份 Excel，能看到草稿批次；点右上角清空按钮，提示文案是「临时 X / 字典 Y」 |
| `89bf7fa` reset 真清 + 自动重灌字典 | 清空后立即 reseed 34 船司 / 140 港口 | 清空后再上传 NGB / 海运 Excel，行数不应再全部 `CARRIER_NOT_FOUND` |
| `3433c5b` 运价导入页 UI 收口 | 删 disclaimer / 重排底部按钮 / 隐邮件入口 | 进入「运价导入」页，没有 disclaimer，只剩 Excel + 聊天截图两个 tab |

**前两次踩过：本地修了，服务器上 git pull 后没重启 / 没 build，"功能不好使"就是这么来的。**

---

## 1. 项目结构（服务器视角）

```
阪急阪神/                              # 仓库根
├── backend/                          # Python 后端（FastAPI）
│   ├── .env                          # ⚠️ 生产环境变量，不入 git
│   ├── .env.example                  # 模板
│   ├── app/                          # 业务代码
│   ├── alembic/                      # DB 迁移
│   ├── alembic.ini
│   ├── hankyu_hanshin.db             # SQLite（如果走 SQLite）
│   ├── uploads/                      # ⚠️ 运价 Excel 落盘目录（必须可写）
│   ├── requirements.txt
│   └── tests/
├── frontend/                         # React 前端（Vite + TS）
│   ├── .env                          # ⚠️ VITE_API_BASE_URL 等，不入 git
│   ├── package.json
│   ├── src/
│   ├── dist/                         # build 产物（部署的就是这个）
│   └── vite.config.ts
├── scripts/
│   └── seed_data.py                  # 字典种子（reset 时被 admin.py 动态加载）
├── docker-compose.yml                # 仅 postgres + redis（业务进程不在里面）
└── DEPLOYMENT.md                     # 本文件
```

---

## 2. 首次部署（全新服务器）

### 2.1 系统依赖

```bash
# Ubuntu 22.04 / 24.04
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip git nginx
# Node 20+
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 2.2 拉代码 + Python venv

```bash
sudo mkdir -p /opt/hankyu && sudo chown -R $USER: /opt/hankyu
cd /opt/hankyu
git clone <repo-url> .
python3.10 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

### 2.3 配后端 .env

```bash
cp backend/.env.example backend/.env
# 然后编辑 backend/.env，最少要填：
# - DATABASE_URL（SQLite 留默认即可；走 PG 改成 postgresql://...）
# - VLLM_BASE_URL / VLLM_API_KEY / VLLM_MODEL（AI Provider）
# - EMAIL_ADDRESS / EMAIL_PASSWORD（邮件 Demo）
# - UPLOAD_DIR=/var/lib/hankyu/uploads     # ★ 强烈建议写绝对路径，原因见 §5
# - APP_ENV=production
# - DEBUG=false
```

**关键：UPLOAD_DIR 必须可写**

```bash
sudo mkdir -p /var/lib/hankyu/uploads
sudo chown -R $USER: /var/lib/hankyu/uploads
sudo chmod -R u+rwX /var/lib/hankyu/uploads
```

### 2.4 初始化数据库 + 灌字典

```bash
cd /opt/hankyu/backend
../.venv/bin/python -m alembic upgrade head
cd /opt/hankyu
.venv/bin/python scripts/seed_data.py
# 期望日志：carriers seed: 34 inserted / ports seed: 140 inserted
```

### 2.5 前端 build

```bash
cd /opt/hankyu/frontend
# 配 .env，最重要的是 API 地址
cat > .env <<'EOF'
VITE_API_BASE_URL=https://your-domain.example.com/api/v1
EOF
npm ci
npm run build
# 产物在 frontend/dist/
```

### 2.6 启动后端（systemd）

`/etc/systemd/system/hankyu-backend.service`：

```ini
[Unit]
Description=Hankyu Hanshin Backend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/hankyu/backend
EnvironmentFile=/opt/hankyu/backend/.env
ExecStart=/opt/hankyu/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

⚠️ `WorkingDirectory=/opt/hankyu/backend` 必须设。即便 `_resolve_upload_dir` 已经把相对路径锚到 backend/，但 `.env` 等加载逻辑仍以 cwd 为准。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hankyu-backend
sudo systemctl status hankyu-backend --no-pager
```

### 2.7 配 nginx 反代

```nginx
server {
  listen 443 ssl http2;
  server_name your-domain.example.com;

  ssl_certificate     /etc/nginx/ssl/your-domain/fullchain.pem;
  ssl_certificate_key /etc/nginx/ssl/your-domain/privkey.pem;

  client_max_body_size 50m;          # ⚠️ 投标包/.msg 文件可能 >10M

  # 前端静态
  root /var/www/hankyu/current;
  index index.html;
  location / { try_files $uri $uri/ /index.html; }

  # 后端 API
  location /api/ {
    proxy_pass         http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;        # AI 兜底解析可能跑 30~90s
  }
}

server {
  listen 80;
  server_name your-domain.example.com;
  return 301 https://$host$request_uri;
}
```

```bash
sudo mkdir -p /var/www/hankyu/current
sudo cp -a /opt/hankyu/frontend/dist/. /var/www/hankyu/current/
sudo chown -R www-data:www-data /var/www/hankyu
sudo nginx -t && sudo systemctl reload nginx
```

---

## 3. 升级部署（已上线，新一版 commit）

**这是最常出问题的环节。每一步都不能跳。**

```bash
cd /opt/hankyu
git fetch && git status                       # 先看现在在哪个 commit
git pull --ff-only                            # 拉最新
```

### 3.1 后端依赖变了？

```bash
git diff HEAD@{1} HEAD -- backend/requirements.txt
# 如果有变化：
.venv/bin/pip install -r backend/requirements.txt
```

### 3.2 数据库迁移变了？

```bash
git diff HEAD@{1} HEAD -- backend/alembic/versions/
# 如果有新增迁移文件：
cd /opt/hankyu/backend
../.venv/bin/python -m alembic upgrade head
cd ..
```

### 3.3 字典/seed 变了？

```bash
git diff HEAD@{1} HEAD -- scripts/seed_data.py backend/app/api/v1/admin.py
# 如果 carriers / ports 字典有新增 → reseed：
.venv/bin/python scripts/seed_data.py
# 或在前端右上角点一次「清空」按钮，admin.py 会自动调 reseed_dictionaries(db)
```

### 3.4 前端代码变了？必 build！

```bash
cd /opt/hankyu/frontend
git diff HEAD@{1} HEAD -- package.json
# 如果 package.json 有变化：
npm ci

npm run build
sudo rm -rf /var/www/hankyu/current
sudo mkdir -p /var/www/hankyu/current
sudo cp -a dist/. /var/www/hankyu/current/
sudo chown -R www-data:www-data /var/www/hankyu
sudo nginx -t && sudo systemctl reload nginx
cd ..
```

> ⚠️⚠️⚠️ **最常见的坑：拉了代码、重启了后端，但忘记 build 前端 + 拷贝 dist。**
> 表现是「修复后部署后还是不好使」——浏览器加载的是旧的 JS bundle。
> 改完前端代码 → `npm run build` → 拷贝 `dist/` 到 `/var/www/hankyu/current/` → reload nginx，
> 这四步少一步都白干。

### 3.5 重启后端

```bash
sudo systemctl restart hankyu-backend
sudo systemctl status hankyu-backend --no-pager --lines=20
```

### 3.6 烟雾测试（必跑）

```bash
# 1) 健康检查
curl -s http://127.0.0.1:8000/api/v1/health || echo "❌ backend down"

# 2) 字典
curl -s 'http://127.0.0.1:8000/api/v1/carriers?only_used=false' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('carriers:', len(d.get('data',{}).get('items', [])))"
# 期望：≥34

# 3) 运价库
curl -s 'http://127.0.0.1:8000/api/v1/freight-rates/stats' \
  | python3 -m json.tool
```

浏览器再过一遍：

- [ ] 登录页能进
- [ ] 仪表盘有数据
- [ ] 「运价导入」页：上传一份 Excel → 进度条会推进到「上传完成」→ 下方批次列表有新批次 → 点开能看预览 → 点「采用」入库成功
- [ ] 「船司/供应商」页：清空后页面空 / 导入后只显命中
- [ ] 「投标包自动填表」端到端能跑通

---

## 4. 「为什么修了还是不好使」常见原因（按出现频率）

### 4.1 前端代码改了，但 dist 没更新
```bash
# 验证：浏览器开发者工具 Network → 看 main-XXXX.js 的 hash
# 如果 hash 跟本地最新 build 不一致 → dist 没拷贝过去
```
**解法**：`npm run build` → 拷 `dist/` → reload nginx。Ctrl+Shift+R 强刷一次。

### 4.2 后端代码改了，但 systemd 没重启
```bash
sudo systemctl status hankyu-backend
# Active: 时间戳 < 你 git pull 的时间 → 没重启
```
**解法**：`sudo systemctl restart hankyu-backend`。

### 4.3 .env 变量名变了，但生产 .env 没同步
```bash
diff <(grep -oE '^[A-Z_]+=' backend/.env.example | sort -u) \
     <(grep -oE '^[A-Z_]+=' backend/.env             | sort -u)
```
**解法**：把 `.env.example` 里新增的 key 补到 `backend/.env`，重启后端。

### 4.4 alembic 没 upgrade
```bash
.venv/bin/python -m alembic -c backend/alembic.ini current
.venv/bin/python -m alembic -c backend/alembic.ini heads
# current ≠ heads → 没 upgrade
```
**解法**：`alembic upgrade head` + 重启后端。

### 4.5 字典被清掉没重灌（reset 路径之外的奇怪状态）
**症状**：导入海运/NGB 运价行数对，但 `CARRIER_NOT_FOUND` 全跳过 0 行入库。
**解法**：
```bash
.venv/bin/python scripts/seed_data.py
# 或在前端右上角点一次「清空」按钮（自动 reseed）
```

### 4.6 uploads 目录不可写
**症状**：上传 Excel 立即 500，日志里 `PermissionError: Cannot write to upload dir`。
**解法**：报错信息里直接给修复命令，照着 `chown -R` + `chmod -R u+rwX` 就行。
**最佳实践**：直接在 `.env` 里写绝对路径 `UPLOAD_DIR=/var/lib/hankyu/uploads` 一劳永逸。

### 4.7 前端 API 地址写错（最坑的隐蔽 bug）
**症状**：浏览器全是 ERR_CONNECTION_REFUSED 到 `localhost:8000`。
**根因**：`frontend/.env` 没设 `VITE_API_BASE_URL`，前端 fallback 到 `${当前 hostname}:8000` 但 nginx 没把 8000 透给外网。
**解法**：在 `frontend/.env` 写 `VITE_API_BASE_URL=https://your-domain.example.com/api/v1` → **重新 build** → 重新部署 dist。
不 build 改 .env 等于没改！

### 4.8 nginx `client_max_body_size` 太小
**症状**：投标包/.msg 文件上传 413 Request Entity Too Large。
**解法**：nginx site config 里加 `client_max_body_size 50m;` → reload。

---

## 5. UPLOAD_DIR 行为说明（务必理解）

代码 `backend/app/services/rate_batch_service.py::_resolve_upload_dir`：

- **绝对路径**（如 `UPLOAD_DIR=/var/lib/hankyu/uploads`）：原样使用。**强烈推荐 prod 这样配**。
- **相对路径**（如默认 `uploads`）：自动锚到 `backend/` 目录，**不**随进程 cwd 漂。

为什么强调？历史踩过：
- systemd 启动时 cwd = `/`，`Path("uploads")` 解析到 `/uploads` → 没权限 500
- 用 docker / IDE / 命令行启动 cwd 各不相同，相对路径解析结果完全不一样

虽然代码已经把相对路径锚定到 backend/，但**生产环境永远写绝对路径**最稳。

---

## 6. 数据库

### 6.1 SQLite（默认）

数据库文件：`backend/hankyu_hanshin.db`。

**注意备份**：升级前先 `cp backend/hankyu_hanshin.db backend/hankyu_hanshin.db.bak.$(date +%Y%m%d-%H%M%S)`。

### 6.2 PostgreSQL（推荐 prod）

```bash
# .env
DATABASE_URL=postgresql://hankyu:<password>@localhost:5432/hankyu_hanshin
```

```bash
sudo -u postgres psql -c "CREATE DATABASE hankyu_hanshin;"
sudo -u postgres psql -c "CREATE USER hankyu WITH PASSWORD '<password>';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE hankyu_hanshin TO hankyu;"
# 然后跑 alembic upgrade head + scripts/seed_data.py
```

切换 DB 后必须重新 `seed_data.py`，不然字典是空的。

---

## 7. AI 参数（运行时可改，无需重启）

后端起来后，进入「系统设置」页可改：
- AI Provider（vllm / anthropic）
- vLLM Base URL / API Key / Model
- 超参（max_tokens / temperature 等）

保存即生效（30s TTL 缓存），**无需改 .env、无需重启后端**。
所以 vLLM 服务搬迁、换 Key、换模型，运维直接在 UI 改即可。

但 **首次部署的默认值** 仍来自 `backend/.env`，所以 .env 里的 `VLLM_*` 必须能用。

---

## 8. 日志位置

```bash
# 后端
sudo journalctl -u hankyu-backend -n 200 --no-pager
sudo journalctl -u hankyu-backend -f        # 跟踪

# nginx
sudo tail -n 100 /var/log/nginx/access.log
sudo tail -n 100 /var/log/nginx/error.log
```

---

## 9. 回滚

```bash
cd /opt/hankyu
git log --oneline -10                       # 找上一个稳定 commit
git checkout <prev-commit>
# 后端
sudo systemctl restart hankyu-backend
# 前端
cd frontend && npm run build
sudo rm -rf /var/www/hankyu/current && sudo cp -a dist/. /var/www/hankyu/current/
sudo systemctl reload nginx
# DB 迁移如果向前升级了 → 必要时手动 alembic downgrade -1
```

---

## 10. 给在服务器上做部署的 AI 助手的提示

如果你是被叫到服务器上"修复 X 功能"的 AI：

1. **先 `git log -5` 和 `git status`**，确认服务器上代码到底是哪个 commit、有没有未提交本地改动。「修复了"清空"还是不好使」——99% 是服务器代码 ≠ 修复的 commit。
2. **修代码不等于修复生效**。后端改完必须 `systemctl restart hankyu-backend`；前端改完必须 `npm run build` + 拷贝 `dist/` + `nginx -s reload`。
3. **不要在生产直接 `git reset --hard` 也不要 `rm -rf uploads/`**，先备份。
4. **`backend/.env` 是生产配置，永远不要覆盖**，只在缺 key 时追加。
5. **检查清单**（任何"功能不好使"先过一遍）：
   - `systemctl status hankyu-backend` → 服务在跑 + 启动时间 > git pull 时间
   - `git rev-parse HEAD` → 跟开发同事核对的 commit 一致
   - `alembic current` == `alembic heads`
   - `curl -I https://<domain>/api/v1/health` → 200
   - 浏览器 Network → main-*.js 的 hash 跟本地 `frontend/dist/` 里的对得上
   - `ls /var/lib/hankyu/uploads`（或 `backend/uploads`）→ 属主是 uvicorn 跑的用户、有写权限
6. 把第 4 节「为什么修了还是不好使」从上往下挨个排除一遍。
