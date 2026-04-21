"""邮件脉络 HTML 报告生成服务。

基于 analyze_emails 的检索结果，调用通义千问 Qwen 提取结构化脉络数据，
并渲染为与 toyota_steel_quality_report.html 风格一致的 HTML 报告。
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Optional
from urllib import error, request


# ────────────────────────────────────────────────────────────────────────
# 对外入口
# ────────────────────────────────────────────────────────────────────────

def generate_report_html(query: str, top_k: int = 15) -> dict:
    """生成 HTML 报告。

    返回: {"filename": str, "html": str, "count": int}
    """
    from app.services.email_search_service import search_emails

    emails = search_emails(query=query, top_k=top_k)
    if not emails:
        html_text = _render_empty(query)
        return {
            "filename": _build_filename(query),
            "html": html_text,
            "count": 0,
        }

    structured = _build_structured(query=query, emails=emails)
    html_text = _render_html(structured)
    return {
        "filename": _build_filename(query),
        "html": html_text,
        "count": len(emails),
    }


# ────────────────────────────────────────────────────────────────────────
# 结构化数据构建
# ────────────────────────────────────────────────────────────────────────

def _build_structured(query: str, emails: list[dict]) -> dict:
    """优先使用 Qwen 输出结构化 JSON；失败则回退到规则提取。"""
    from app.core.config import settings

    default_struct = _fallback_struct(query, emails)

    if not settings.qwen_api_key:
        return default_struct

    try:
        ai_struct = _qwen_structure(query, emails)
        # 用 AI 结果覆盖默认结构的关键字段
        default_struct.update({k: v for k, v in ai_struct.items() if v})
        return default_struct
    except Exception as exc:  # pragma: no cover - 网络异常
        print(f"[EmailReport] Qwen 结构化失败，使用回退: {exc}")
        return default_struct


def _qwen_structure(query: str, emails: list[dict]) -> dict:
    from app.core.config import settings

    email_context = ""
    for index, item in enumerate(emails, 1):
        email_context += f"\n--- 邮件 {index} ---\n"
        email_context += f"日期: {item.get('date', '')}\n"
        email_context += f"发件人: {item.get('from_name', '')} <{item.get('from', '')}>\n"
        email_context += f"收件人: {item.get('to', '')}\n"
        email_context += f"主题: {item.get('subject', '')}\n"
        email_context += f"内容:\n{(item.get('content') or '')[:1500]}\n"

    system_prompt = (
        "你是严谨的企业邮件分析助手。请根据提供的邮件列表，围绕用户查询生成一份结构化 JSON。"
        "只输出 JSON，不要 markdown 代码块，不要其它说明。"
    )

    json_schema_hint = """请严格按以下 JSON 结构输出：
{
  "title": "报告主标题（含emoji，简洁有力）",
  "subtitle": "一句话说明数据来源与范围",
  "meta_badges": ["📅 时间跨度：...", "🏢 客户：...", "🤝 主题：..."],
  "summary": {
    "related_count": 数字,
    "span_days": 数字,
    "milestones": 数字,
    "participants": 数字
  },
  "timeline": [
    {
      "date_label": "2026年3月3日（周二）",
      "dot_style": "primary",   // 可选 primary|accent|green|orange
      "title": "【里程碑①】...",
      "sender": "赵良禹（DHC）",
      "receiver": "藤井弦二郎（TJTS）",
      "summary": "概述一句话",
      "bullets": ["要点1", "要点2", "要点3"],
      "tags": [{"text": "首次报告", "style": "default"}]
    }
  ],
  "topics": [
    {"title": "① 原材料检查", "items": ["要点1", "要点2"]}
  ],
  "participants": [
    {"name": "赵良禹", "role": "DHC · 项目负责人"}
  ],
  "status_steps": [
    {"text": "现场调查", "status": "done"},
    {"text": "方案初报", "status": "done"},
    {"text": "等待反馈", "status": "doing"},
    {"text": "方案确认", "status": "todo"}
  ],
  "conclusion_items": [
    {"label": "✅ 已完成", "content": "· 项目1\\n· 项目2"},
    {"label": "⏳ 进行中", "content": "· 项目1"},
    {"label": "⚠ 关键风险点", "content": "· 风险1"},
    {"label": "🎯 建议下一步", "content": "· 建议1"}
  ]
}

要求：
1. timeline 按时间升序；dot_style 对关键里程碑用 accent 或 green
2. topics 数量 2~4 个
3. tags.style 可选 default|red|green|orange
4. status_steps 按项目阶段递进
5. 所有字段都要填，不要留空"""

    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"【用户查询】\n{query}\n\n"
                    f"【相关邮件】{email_context}\n\n"
                    f"{json_schema_hint}"
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"},
    }

    req = request.Request(
        url=f"{settings.qwen_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.qwen_api_key}",
        },
        method="POST",
    )

    with request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))

    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Qwen 返回为空")

    # 去掉可能出现的 ```json 代码围栏
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return json.loads(content)


def _fallback_struct(query: str, emails: list[dict]) -> dict:
    """无 Qwen 时的规则化结构。"""
    sorted_emails = sorted(emails, key=lambda it: it.get("date", ""))
    dates = [e.get("date", "")[:10] for e in sorted_emails if e.get("date")]

    span_days = 0
    if len(dates) >= 2:
        try:
            d1 = datetime.strptime(dates[0], "%Y-%m-%d")
            d2 = datetime.strptime(dates[-1], "%Y-%m-%d")
            span_days = (d2 - d1).days
        except ValueError:
            span_days = 0

    timeline = []
    for email in sorted_emails:
        date_raw = email.get("date", "")[:10]
        date_label = _format_date_label(date_raw)
        body_snippet = (email.get("content") or "").strip().splitlines()
        bullets = [line.strip("-•· ").strip() for line in body_snippet if line.strip()][:4]
        timeline.append(
            {
                "date_label": date_label or "-",
                "dot_style": "primary",
                "title": email.get("subject") or "(无主题)",
                "sender": email.get("from_name") or email.get("from", ""),
                "receiver": email.get("to", ""),
                "summary": "",
                "bullets": bullets,
                "tags": [],
            }
        )

    # 标记首尾为里程碑
    if timeline:
        timeline[0]["dot_style"] = "accent"
        timeline[-1]["dot_style"] = "green"

    people = sorted({(e.get("from_name") or e.get("from", "")).strip() for e in emails if e.get("from_name") or e.get("from")})
    participants = [{"name": name, "role": ""} for name in people if name]

    return {
        "title": "📊 邮件脉络分析报告",
        "subtitle": f"基于检索指令「{query}」，共汇总 {len(emails)} 封相关邮件",
        "meta_badges": [
            f"📅 时间范围：{dates[0] if dates else '-'} — {dates[-1] if dates else '-'}",
            f"✉ 邮件数量：{len(emails)} 封",
            f"🔍 检索词：{query}",
        ],
        "summary": {
            "related_count": len(emails),
            "span_days": span_days,
            "milestones": min(3, len(emails)),
            "participants": len(participants),
        },
        "timeline": timeline,
        "topics": [
            {
                "title": "📌 主要议题",
                "items": [e.get("subject") or "(无主题)" for e in emails[:4]],
            }
        ],
        "participants": participants,
        "status_steps": [
            {"text": "邮件收集", "status": "done"},
            {"text": "AI 分析", "status": "done"},
            {"text": "人工复核", "status": "doing"},
            {"text": "行动决策", "status": "todo"},
        ],
        "conclusion_items": [
            {
                "label": "✅ 已完成",
                "content": "· 相关邮件检索与聚合\n· 时间线自动还原",
            },
            {
                "label": "⏳ 进行中",
                "content": "· 业务方复核邮件内容\n· 关键信息人工确认",
            },
            {
                "label": "⚠ 注意事项",
                "content": "· 报告由 AI 自动生成，关键数据请以原邮件为准",
            },
            {
                "label": "🎯 建议下一步",
                "content": "· 跟进未回复邮件\n· 整理决策项并分派责任人",
            },
        ],
    }


def _format_date_label(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return f"{dt.year}年{dt.month}月{dt.day}日（{weekdays[dt.weekday()]}）"


def _build_filename(query: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", query).strip("_") or "email_report"
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{safe[:30]}_{ts}.html"


# ────────────────────────────────────────────────────────────────────────
# HTML 渲染
# ────────────────────────────────────────────────────────────────────────

_CSS = """
:root{--primary:#1a3c6e;--accent:#e8401c;--green:#1e7a45;--orange:#e07b10;--bg:#f5f6f8;--card:#fff;--border:#dde2ea;--text:#1d2535;--sub:#6b7a9a;--tag-bg:#eef2ff;--tag-text:#3b5bdb;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);line-height:1.7;}
.header{background:linear-gradient(135deg,#0d2b5e 0%,#1a3c6e 60%,#2d5a9e 100%);color:#fff;padding:40px 48px 36px;}
.header-meta{font-size:13px;opacity:.7;margin-bottom:10px;letter-spacing:.5px;}
.header h1{font-size:28px;font-weight:700;margin-bottom:8px;}
.header p{font-size:15px;opacity:.85;}
.header-badges{margin-top:18px;display:flex;gap:10px;flex-wrap:wrap;}
.badge{display:inline-flex;align-items:center;gap:5px;background:rgba(255,255,255,.15);border-radius:20px;padding:4px 12px;font-size:12px;font-weight:500;}
.container{max-width:960px;margin:0 auto;padding:32px 24px 60px;}
.section-title{font-size:17px;font-weight:700;color:var(--primary);border-left:4px solid var(--accent);padding-left:12px;margin:36px 0 16px;}
.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:8px;}
.sum-card{background:var(--card);border-radius:10px;padding:18px 16px;border:1px solid var(--border);text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.05);}
.sum-card .num{font-size:30px;font-weight:800;color:var(--primary);}
.sum-card .label{font-size:12px;color:var(--sub);margin-top:4px;}
.timeline{position:relative;padding-left:36px;}
.timeline::before{content:'';position:absolute;left:10px;top:0;bottom:0;width:2px;background:linear-gradient(to bottom,var(--primary),#c9d4f0);}
.tl-item{position:relative;margin-bottom:28px;}
.tl-dot{position:absolute;left:-32px;top:5px;width:16px;height:16px;border-radius:50%;background:var(--primary);border:3px solid #fff;box-shadow:0 0 0 2px var(--primary);}
.tl-dot.accent{background:var(--accent);box-shadow:0 0 0 2px var(--accent);}
.tl-dot.green{background:var(--green);box-shadow:0 0 0 2px var(--green);}
.tl-dot.orange{background:var(--orange);box-shadow:0 0 0 2px var(--orange);}
.tl-card{background:var(--card);border-radius:10px;padding:18px 20px;border:1px solid var(--border);box-shadow:0 1px 4px rgba(0,0,0,.05);}
.tl-date{font-size:12px;color:var(--sub);font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;}
.tl-title{font-size:15px;font-weight:700;color:var(--primary);margin-bottom:8px;}
.tl-meta{font-size:12px;color:var(--sub);margin-bottom:10px;}
.tl-meta span{margin-right:14px;}
.tl-body{font-size:13.5px;color:#3a4460;}
.tl-body ul{padding-left:18px;margin-top:6px;}
.tl-body li{margin-bottom:4px;}
.tag{display:inline-block;background:var(--tag-bg);color:var(--tag-text);border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;margin-right:4px;margin-bottom:4px;}
.tag.red{background:#fff0ee;color:#c0392b;}
.tag.green{background:#edfaf3;color:#1e7a45;}
.tag.orange{background:#fff8ec;color:#b35a00;}
.topic-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.topic-card{background:var(--card);border-radius:10px;padding:20px;border:1px solid var(--border);box-shadow:0 1px 4px rgba(0,0,0,.05);}
.topic-card h4{font-size:14px;font-weight:700;color:var(--primary);margin-bottom:10px;}
.topic-card p,.topic-card li{font-size:13px;color:#3a4460;}
.topic-card ul{padding-left:16px;}
.topic-card li{margin-bottom:5px;}
.people-list{display:flex;flex-wrap:wrap;gap:10px;}
.person{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 14px;min-width:200px;flex:1;box-shadow:0 1px 4px rgba(0,0,0,.04);}
.person .name{font-size:14px;font-weight:700;color:var(--primary);}
.person .role{font-size:12px;color:var(--sub);margin-top:2px;}
.conclusion{background:linear-gradient(135deg,#f0f4ff,#eaf7ef);border-radius:12px;padding:24px 28px;border:1px solid #c9d8f5;}
.conclusion h4{font-size:16px;font-weight:700;color:var(--primary);margin-bottom:14px;}
.conclusion-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.c-item{background:#fff;border-radius:8px;padding:14px 16px;border:1px solid #dde8fa;}
.c-item .c-label{font-size:12px;font-weight:700;color:var(--sub);margin-bottom:6px;letter-spacing:.4px;}
.c-item .c-val{font-size:13px;color:var(--text);white-space:pre-line;}
.status-bar{display:flex;gap:6px;margin-top:16px;align-items:center;flex-wrap:wrap;}
.step{display:flex;align-items:center;gap:6px;background:#fff;border-radius:20px;padding:5px 12px;font-size:12px;border:1px solid var(--border);}
.step .dot{width:8px;height:8px;border-radius:50%;}
.step.done .dot{background:var(--green);}
.step.doing .dot{background:var(--orange);}
.step.todo .dot{background:#ccc;}
.arrow{color:var(--sub);font-size:14px;}
footer{text-align:center;font-size:12px;color:var(--sub);padding:20px 0 10px;border-top:1px solid var(--border);margin-top:40px;}
"""


def _esc(text: Optional[str]) -> str:
    return html.escape(str(text or ""), quote=False)


def _render_empty(query: str) -> str:
    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
        f"<title>邮件脉络报告 · 无结果</title><style>{_CSS}</style></head><body>"
        f"<div class='header'><h1>📊 邮件脉络分析报告</h1>"
        f"<p>查询「{_esc(query)}」未检索到相关邮件，无法生成报告。</p></div>"
        "</body></html>"
    )


def _render_html(data: dict) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = _esc(data.get("title") or "📊 邮件脉络分析报告")
    subtitle = _esc(data.get("subtitle") or "")
    badges_html = "".join(
        f"<span class='badge'>{_esc(b)}</span>" for b in (data.get("meta_badges") or [])
    )

    summary = data.get("summary") or {}
    summary_html = "".join(
        f"<div class='sum-card'><div class='num'>{_esc(summary.get(key, '-'))}</div><div class='label'>{_esc(label)}</div></div>"
        for key, label in [
            ("related_count", "相关邮件数"),
            ("span_days", "时间跨度(天)"),
            ("milestones", "关键里程碑"),
            ("participants", "参与人员"),
        ]
    )

    timeline_html = _render_timeline(data.get("timeline") or [])
    topics_html = _render_topics(data.get("topics") or [])
    people_html = _render_participants(data.get("participants") or [])
    status_html = _render_status(data.get("status_steps") or [])
    conclusion_html = _render_conclusion(data.get("conclusion_items") or [])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="header">
  <div class="header-meta">邮件脉络分析报告 · 生成时间：{now_str}</div>
  <h1>{title}</h1>
  <p>{subtitle}</p>
  <div class="header-badges">{badges_html}</div>
</div>
<div class="container">
  <div class="section-title">📌 数据总览</div>
  <div class="summary-grid">{summary_html}</div>

  <div class="section-title">🗓️ 时间脉络（按邮件时序还原）</div>
  <div class="timeline">{timeline_html}</div>

  <div class="section-title">🔍 核心议题</div>
  <div class="topic-grid">{topics_html}</div>

  <div class="section-title">👥 主要参与人员</div>
  <div class="people-list">{people_html}</div>

  <div class="section-title">📈 项目进展状态 &amp; 待办</div>
  <div class="conclusion">
    <h4>当前项目阶段</h4>
    <div class="status-bar">{status_html}</div>
    <div class="conclusion-grid" style="margin-top:18px;">{conclusion_html}</div>
  </div>

  <footer>报告由 WorkBuddy AI 自动生成 · 数据来源：邮件索引库 · 生成时间：{now_str}</footer>
</div>
</body>
</html>
"""


def _render_timeline(items: list[dict]) -> str:
    if not items:
        return "<p style='color:#6b7a9a;padding:20px;'>暂无时间线数据</p>"

    blocks = []
    for item in items:
        dot_style = item.get("dot_style") or ""
        dot_class = f"tl-dot {dot_style}" if dot_style in {"accent", "green", "orange"} else "tl-dot"

        bullets = item.get("bullets") or []
        bullets_html = ""
        if bullets:
            bullets_html = "<ul>" + "".join(f"<li>{_esc(b)}</li>" for b in bullets) + "</ul>"

        tags = item.get("tags") or []
        tags_html = ""
        if tags:
            tags_html = "<div style='margin-top:10px;'>" + "".join(
                f"<span class='tag {_esc(t.get('style', '')) if t.get('style') in {'red','green','orange'} else ''}'>{_esc(t.get('text', ''))}</span>"
                for t in tags if t.get("text")
            ) + "</div>"

        meta_parts = []
        if item.get("sender"):
            meta_parts.append(f"<span>✉ 发件人：{_esc(item.get('sender'))}</span>")
        if item.get("receiver"):
            meta_parts.append(f"<span>📨 收件人：{_esc(item.get('receiver'))}</span>")
        meta_html = "".join(meta_parts)

        summary_html = f"<p>{_esc(item.get('summary'))}</p>" if item.get("summary") else ""

        blocks.append(f"""
<div class="tl-item">
  <div class="{dot_class}"></div>
  <div class="tl-card">
    <div class="tl-date">{_esc(item.get('date_label'))}</div>
    <div class="tl-title">{_esc(item.get('title'))}</div>
    <div class="tl-meta">{meta_html}</div>
    <div class="tl-body">{summary_html}{bullets_html}{tags_html}</div>
  </div>
</div>""")
    return "\n".join(blocks)


def _render_topics(topics: list[dict]) -> str:
    if not topics:
        return ""
    blocks = []
    for topic in topics:
        items_html = "".join(f"<li>{_esc(i)}</li>" for i in (topic.get("items") or []))
        blocks.append(
            f"<div class='topic-card'><h4>{_esc(topic.get('title'))}</h4><ul>{items_html}</ul></div>"
        )
    return "\n".join(blocks)


def _render_participants(people: list[dict]) -> str:
    if not people:
        return "<p style='color:#6b7a9a;padding:10px;'>未识别到参与人员</p>"
    return "\n".join(
        f"<div class='person'><div class='name'>{_esc(p.get('name'))}</div><div class='role'>{_esc(p.get('role'))}</div></div>"
        for p in people
    )


def _render_status(steps: list[dict]) -> str:
    if not steps:
        return ""
    parts = []
    for i, step in enumerate(steps):
        status = step.get("status") or "todo"
        status = status if status in {"done", "doing", "todo"} else "todo"
        if i > 0:
            parts.append("<div class='arrow'>→</div>")
        parts.append(f"<div class='step {status}'><span class='dot'></span>{_esc(step.get('text'))}</div>")
    return "".join(parts)


def _render_conclusion(items: list[dict]) -> str:
    if not items:
        return ""
    return "\n".join(
        f"<div class='c-item'><div class='c-label'>{_esc(item.get('label'))}</div><div class='c-val'>{_esc(item.get('content'))}</div></div>"
        for item in items
    )
