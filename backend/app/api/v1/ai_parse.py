"""AI 解析 API — 邮件文本解析 + WeChat 截图解析 + 邮箱直连识别"""
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.schemas.common import ApiResponse
from app.services.email_text_parser import parse_email_text
from app.services.wechat_image_parser import parse_wechat_image
from app.services.rate_parser import import_parsed_rates

router = APIRouter(prefix="/ai", tags=["ai-parse"])

# 共享解析缓存（与 rates.py 使用同一个，通过导入）
from app.api.v1.rates import _parse_cache

# 邮箱原邮件缓存：list 接口拉到的 body 临时存这里，parse 接口复用，避免重复 IMAP 拉取
# key 是 base64-encoded message id，value 是完整邮件 dict
_inbox_email_cache: dict[str, dict] = {}


@router.post("/parse-email-text")
def api_parse_email_text(
    text: str = Form(..., description="邮件文本内容"),
    db: Session = Depends(get_db),
):
    """AI 解析邮件文本中的运价信息"""
    if not text.strip():
        return ApiResponse(code=400, message="文本内容不能为空")

    result = parse_email_text(text, db)

    if not result["parsed_rows"]:
        return ApiResponse(
            code=200,
            data=result,
            message=f"未能提取到费率数据。{'; '.join(result.get('warnings', []))}",
        )

    # 缓存解析结果（供后续确认导入）
    _parse_cache[result["batch_id"]] = result

    # 构建预览
    preview_rows = _build_preview(result)

    return ApiResponse(data={
        "batch_id": result["batch_id"],
        "file_name": "email_text_input",
        "source_type": "email_text",
        "carrier_code": result.get("carrier_code", ""),
        "total_rows": result["total_rows"],
        "preview_rows": preview_rows,
        "warnings": result.get("warnings", []),
        "sheets": [],
    })


@router.post("/parse-wechat-image")
async def api_parse_wechat_image(
    file: UploadFile = File(...),
    context: str = Form("", description="补充上下文（可选）"),
    db: Session = Depends(get_db),
):
    """AI 解析微信/QQ 截图中的运价信息"""
    # 验证文件类型
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return ApiResponse(code=400, message="仅支持图片文件 (PNG/JPG/GIF/WebP)")

    # 保存图片
    os.makedirs(settings.upload_dir, exist_ok=True)
    save_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = os.path.join(settings.upload_dir, save_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    result = parse_wechat_image(save_path, db, extra_context=context)

    if not result["parsed_rows"]:
        return ApiResponse(
            code=200,
            data=result,
            message=f"未能从截图中提取费率。{'; '.join(result.get('warnings', []))}",
        )

    _parse_cache[result["batch_id"]] = result

    preview_rows = _build_preview(result)

    return ApiResponse(data={
        "batch_id": result["batch_id"],
        "file_name": result.get("file_name", file.filename),
        "source_type": "wechat_image",
        "carrier_code": result.get("carrier_code", ""),
        "total_rows": result["total_rows"],
        "preview_rows": preview_rows,
        "warnings": result.get("warnings", []),
        "sheets": [],
    })


@router.get("/inbox-emails")
def api_list_inbox_emails(
    limit: int = Query(20, ge=1, le=100, description="拉取邮件数量"),
    since_date: str | None = Query(None, description="起始日期 YYYY-MM-DD"),
):
    """从配置的 IMAP 邮箱拉取最近邮件列表（含正文 snippet）。

    返回结构精简后供前端选择，正文同时在服务端缓存以便 parse 接口直接复用。
    """
    from app.services.email_fetcher import fetch_emails

    try:
        emails = fetch_emails(
            limit=limit,
            since_date=since_date,
            include_image_attachments=True,
        )
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(code=500, message=f"邮箱拉取失败: {exc}")

    # 用 message id 的 hash 作为 cache key，避免特殊字符
    items = []
    for raw in emails:
        cache_key = uuid.uuid5(uuid.NAMESPACE_URL, raw.get("id") or "").hex
        _inbox_email_cache[cache_key] = raw

        body = raw.get("body") or ""
        snippet = body.strip().replace("\n", " ")
        if len(snippet) > 200:
            snippet = snippet[:200] + "…"

        # 仅对外暴露图片附件的元数据，二进制留在服务端缓存
        image_attachments = raw.get("image_attachments") or []
        image_meta = [
            {
                "index": idx,
                "filename": img.get("filename", ""),
                "content_type": img.get("content_type", ""),
                "size": img.get("size", 0),
            }
            for idx, img in enumerate(image_attachments)
        ]

        items.append({
            "cache_key": cache_key,
            "id": raw.get("id", ""),
            "subject": raw.get("subject", ""),
            "from": raw.get("from", ""),
            "from_name": raw.get("from_name", ""),
            "date": raw.get("date", ""),
            "snippet": snippet,
            "has_attachment": raw.get("has_attachment", False),
            "attachment_names": raw.get("attachment_names", []),
            "image_attachments": image_meta,
            "folder": raw.get("folder", ""),
            "body_length": len(body),
        })

    return ApiResponse(data={
        "total": len(items),
        "emails": items,
    })


@router.post("/parse-inbox-email")
def api_parse_inbox_email(
    cache_key: str = Form(..., description="邮件缓存 key（来自 /inbox-emails 列表）"),
    db: Session = Depends(get_db),
):
    """对邮箱中选定的某封邮件进行 AI 费率提取。

    复用 email_text_parser 的同一条链路，结果落到 _parse_cache 后由
    /ai/confirm 完成入库。
    """
    cached = _inbox_email_cache.get(cache_key)
    if not cached:
        return ApiResponse(code=404, message="邮件缓存已过期，请先重新拉取邮件列表")

    body = cached.get("body") or ""
    if not body.strip():
        return ApiResponse(code=400, message="该邮件正文为空，无法识别")

    # 把发件人/主题/日期一起塞进 AI 上下文，便于推断船司与时效
    subject = cached.get("subject", "")
    from_name = cached.get("from_name") or cached.get("from", "")
    date_str = (cached.get("date") or "")[:10]
    enriched_text = (
        f"【邮件主题】{subject}\n"
        f"【发件人】{from_name}\n"
        f"【日期】{date_str}\n\n"
        f"{body}"
    )

    result = parse_email_text(enriched_text, db)

    if not result["parsed_rows"]:
        return ApiResponse(
            code=200,
            data=result,
            message=f"未能从邮件中提取到费率。{'; '.join(result.get('warnings', []))}",
        )

    # 用「邮箱直连」标签区分前端展示，但底层 row source_type 仍走 email_text 以匹配 DB 枚举
    safe_subject = (subject[:40] or "inbox_email").replace("/", "_").replace("\\", "_")
    result["file_name"] = f"📧 {safe_subject}"
    for row in result["parsed_rows"]:
        row["source_file"] = result["file_name"]
        # row["source_type"] 保持 "email_text" 不变，避免触发 SourceType 枚举校验失败

    _parse_cache[result["batch_id"]] = result

    preview_rows = _build_preview(result)

    return ApiResponse(data={
        "batch_id": result["batch_id"],
        "file_name": result["file_name"],
        "source_type": "inbox_email",  # 仅前端展示用，DB 实际写入仍是 email_text
        "carrier_code": result.get("carrier_code", ""),
        "total_rows": result["total_rows"],
        "preview_rows": preview_rows,
        "warnings": result.get("warnings", []),
        "sheets": [],
        "email_meta": {
            "subject": subject,
            "from": from_name,
            "date": date_str,
        },
    })


@router.post("/parse-inbox-attachment")
def api_parse_inbox_attachment(
    cache_key: str = Form(..., description="邮件缓存 key"),
    attachment_index: int = Form(..., description="image_attachments 数组下标"),
    db: Session = Depends(get_db),
):
    """对邮件中的某张图片附件运行 AI 视觉识别。

    复用 wechat_image_parser 的链路：把附件二进制写入 upload_dir，
    交给 parse_wechat_image，然后落到 _parse_cache 等待用户确认导入。
    """
    cached = _inbox_email_cache.get(cache_key)
    if not cached:
        return ApiResponse(code=404, message="邮件缓存已过期，请先重新拉取邮件列表")

    image_list = cached.get("image_attachments") or []
    if attachment_index < 0 or attachment_index >= len(image_list):
        return ApiResponse(code=400, message="附件下标越界")

    image = image_list[attachment_index]
    data: bytes = image.get("data") or b""
    if not data:
        return ApiResponse(code=400, message="附件内容为空")

    # 写入临时文件以便复用 parse_wechat_image(image_path)
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = image.get("filename", f"attachment_{attachment_index}.png")
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    save_name = f"inbox_{uuid.uuid4().hex[:8]}_{safe_name}"
    save_path = os.path.join(settings.upload_dir, save_name)
    with open(save_path, "wb") as f:
        f.write(data)

    subject = cached.get("subject", "")
    from_name = cached.get("from_name") or cached.get("from", "")
    extra_context = f"该图片来自邮件「{subject}」，发件人 {from_name}。"

    result = parse_wechat_image(save_path, db, extra_context=extra_context)

    if not result["parsed_rows"]:
        return ApiResponse(
            code=200,
            data=result,
            message=f"未能从邮件附件图片中提取费率。{'; '.join(result.get('warnings', []))}",
        )

    # 标记为「邮箱附件图片」便于前端区分；DB 行 source_type 仍然落 wechat_image
    safe_subject = (subject[:30] or "inbox_image").replace("/", "_").replace("\\", "_")
    result["file_name"] = f"📎 {safe_subject} - {image.get('filename', '')}"
    for row in result["parsed_rows"]:
        row["source_file"] = result["file_name"]

    _parse_cache[result["batch_id"]] = result

    preview_rows = _build_preview(result)

    return ApiResponse(data={
        "batch_id": result["batch_id"],
        "file_name": result["file_name"],
        "source_type": "inbox_attachment",  # 仅前端展示，DB 实际写入仍是 wechat_image
        "carrier_code": result.get("carrier_code", ""),
        "total_rows": result["total_rows"],
        "preview_rows": preview_rows,
        "warnings": result.get("warnings", []),
        "sheets": [],
        "email_meta": {
            "subject": subject,
            "from": from_name,
            "attachment": image.get("filename", ""),
        },
    })


@router.post("/upload-msg-file")
async def api_upload_msg_file(
    file: UploadFile = File(..., description="本地 Outlook .msg 邮件文件"),
):
    """上传本地离线 .msg 邮件文件，落到 inbox 缓存以复用 parse-inbox-email / -attachment 链路。

    .msg 解析后的 dict 与 fetch_emails 返回结构保持一致，因此前端可以
    直接调用 /ai/parse-inbox-email（解析正文）或 /ai/parse-inbox-attachment
    （解析图片附件），无需新增解析接口。
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext != ".msg":
        return ApiResponse(code=400, message="仅支持 Outlook .msg 文件")

    try:
        import extract_msg  # 延迟导入，避免冷启动开销
    except ImportError:
        return ApiResponse(code=500, message="未安装 extract-msg 依赖，请 pip install extract-msg")

    # 落盘后再让 extract_msg 打开，避免它对 BytesIO 兼容性问题
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = (file.filename or "uploaded.msg").replace("/", "_").replace("\\", "_")
    save_name = f"msg_{uuid.uuid4().hex[:8]}_{safe_name}"
    save_path = os.path.join(settings.upload_dir, save_name)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    try:
        msg = extract_msg.openMsg(save_path)
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(code=400, message=f"解析 .msg 文件失败: {exc}")

    subject = (msg.subject or "").strip()
    sender = (msg.sender or "").strip()
    # extract_msg 给的 sender 通常是 "Name <addr>" 形式
    from_name = sender
    from_addr = sender
    if "<" in sender and ">" in sender:
        try:
            from_name = sender.split("<", 1)[0].strip(' "')
            from_addr = sender.split("<", 1)[1].rstrip(">").strip()
        except Exception:  # noqa: BLE001
            pass

    date_iso = ""
    if msg.date:
        try:
            date_iso = msg.date.isoformat() if hasattr(msg.date, "isoformat") else str(msg.date)
        except Exception:  # noqa: BLE001
            date_iso = str(msg.date)

    body = (msg.body or "").strip()

    # 收集附件：分离图片附件（用于 AI 视觉识别）与普通附件名
    image_attachments: list[dict] = []
    attachment_names: list[str] = []
    for att in msg.attachments:
        att_name = att.longFilename or att.shortFilename or ""
        if not att_name:
            continue
        attachment_names.append(att_name)
        ext_lower = os.path.splitext(att_name)[1].lower()
        if ext_lower in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            try:
                data: bytes = att.data or b""
            except Exception:  # noqa: BLE001
                data = b""
            if data:
                image_attachments.append({
                    "filename": att_name,
                    "content_type": f"image/{ext_lower.lstrip('.')}",
                    "size": len(data),
                    "data": data,
                })

    msg.close()

    # 构造与 fetch_emails 完全一致的 dict
    message_id = f"msg-local-{uuid.uuid4().hex}"
    cached = {
        "id": message_id,
        "from": from_addr,
        "from_name": from_name,
        "to": "",
        "cc": "",
        "date": date_iso,
        "subject": subject,
        "body": body[:5000],
        "has_attachment": bool(attachment_names),
        "attachment_names": attachment_names,
        "image_attachments": image_attachments,
        "folder": "local-msg",
    }
    cache_key = uuid.uuid5(uuid.NAMESPACE_URL, message_id).hex
    _inbox_email_cache[cache_key] = cached

    snippet = body.replace("\n", " ")[:200]
    if len(body) > 200:
        snippet += "…"

    return ApiResponse(data={
        "cache_key": cache_key,
        "id": message_id,
        "subject": subject,
        "from": from_addr,
        "from_name": from_name,
        "date": date_iso,
        "snippet": snippet,
        "has_attachment": cached["has_attachment"],
        "attachment_names": attachment_names,
        "image_attachments": [
            {
                "index": idx,
                "filename": img["filename"],
                "content_type": img["content_type"],
                "size": img["size"],
            }
            for idx, img in enumerate(image_attachments)
        ],
        "folder": "local-msg",
        "body_length": len(body),
    })


@router.post("/confirm")
def api_confirm_import(
    batch_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """确认导入 AI 解析结果到数据库（共用 rates 的 confirm 逻辑）"""
    parsed_data = _parse_cache.get(batch_id)
    if not parsed_data:
        return ApiResponse(code=404, message=f"批次 {batch_id} 不存在或已过期")

    result = import_parsed_rates(parsed_data, db)
    _parse_cache.pop(batch_id, None)

    return ApiResponse(data=result)


def _build_preview(result: dict) -> list[dict]:
    """将解析结果转为前端预览格式"""
    all_rows = result.get("parsed_rows", [])
    preview_rows = []
    for r in all_rows[:50]:
        preview_rows.append({
            "origin_port": r.get("origin_port_name", ""),
            "destination_port": r.get("destination_port_name", ""),
            "carrier": r.get("carrier_name", result.get("carrier_code", "")),
            "container_20gp": str(r["container_20gp"]) if r.get("container_20gp") else None,
            "container_40gp": str(r["container_40gp"]) if r.get("container_40gp") else None,
            "container_40hq": str(r["container_40hq"]) if r.get("container_40hq") else None,
            "container_45": str(r["container_45"]) if r.get("container_45") else None,
            "baf_20": str(r["baf_20"]) if r.get("baf_20") else None,
            "baf_40": str(r["baf_40"]) if r.get("baf_40") else None,
            "lss_20": str(r["lss_20"]) if r.get("lss_20") else None,
            "lss_40": str(r["lss_40"]) if r.get("lss_40") else None,
            "valid_from": str(r["valid_from"]) if r.get("valid_from") else None,
            "valid_to": str(r["valid_to"]) if r.get("valid_to") else None,
            "transit_days": str(r["transit_days"]) if r.get("transit_days") else None,
            "remarks": r.get("remarks"),
            "service_code": r.get("service_code"),
        })
    return preview_rows
