# T-B2 TODO — bidding_requests / bidding_row_reports 表迁移

**状态**：本轮（T-B1..T-B4 打地基轮）**推迟**。
**原因**：当前批次仅实现 T-B1（entities/protocols）、T-B3（RateRepository，纯读 Step1 既有表）、
T-B4（CustomerAProfile.parse，纯内存解析）。前四步 **不需要** 新表就能跑通解析 + 检索验收点
V-B01..V-B15。新表的消费方 `service.py` 会话持久化在 T-B9 才落地。

**待补内容**（接手人见架构任务单 §13）：
1. 新建 `backend/alembic/versions/20260423_0001_step2_bidding_models.py`
2. 建表：`bidding_requests`（含 status enum、parsed_pkg_json）、`bidding_row_reports`（含 候选追溯、overridden_by/at、constraint_hits JSON）
3. 对应 SQLAlchemy model：`backend/app/models/bidding_request.py`、`backend/app/models/bidding_row_report.py`
4. 验收点：迁移可 `upgrade` + `downgrade` 双向、对 Step1 表无任何影响（red line 1）。

**落地时机**：T-B5 + T-B9 合并批次（RateMatcher + service 编排）时一起加。
