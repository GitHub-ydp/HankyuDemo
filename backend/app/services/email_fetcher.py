"""IMAP 邮件抓取服务，从企业邮箱拉取邮件。"""
import email
import imaplib
import re
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

from app.core.config import settings


def _normalize_charset(charset: Optional[str]) -> str:
    """规整邮件里不可靠的 charset 标记。"""
    if not charset:
        return "utf-8"

    normalized = charset.strip().strip('"').lower()
    if normalized in {"unknown-8bit", "unknown", "x-unknown", "8bit"}:
        return "utf-8"
    return normalized


def _decode_bytes(payload: Optional[bytes], charset: Optional[str]) -> str:
    """按候选编码顺序解码，尽量避免因脏邮件中断抓取。"""
    if payload is None:
        return ""

    candidates = [
        _normalize_charset(charset),
        "utf-8",
        "gb18030",
        "iso-2022-jp",
        "latin-1",
    ]

    tried = set()
    for candidate in candidates:
        if candidate in tried:
            continue
        tried.add(candidate)
        try:
            return payload.decode(candidate, errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue

    return payload.decode("utf-8", errors="replace")


def _decode_header_value(value: str) -> str:
    """解码邮件头部，兼容 MIME 编码的中日文。"""
    if not value:
        return ""

    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(_decode_bytes(part, charset))
        else:
            result.append(part)
    return " ".join(result)


def _decode_email_address(addr: str) -> tuple[str, str]:
    """解析邮件地址，返回 (显示名, 邮箱地址)。"""
    if not addr:
        return ("", "")

    decoded = _decode_header_value(addr)
    match = re.match(r"(.+?)\s*<(.+?)>", decoded)
    if match:
        return (match.group(1).strip().strip('"'), match.group(2).strip())
    return ("", decoded.strip())


def _get_email_body(msg: email.message.Message) -> str:
    """提取邮件正文，优先纯文本，其次 HTML 去标签。"""
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                try:
                    body = _decode_bytes(
                        part.get_payload(decode=True),
                        part.get_content_charset(),
                    )
                    break
                except Exception:
                    continue

            if content_type == "text/html" and not body:
                try:
                    html = _decode_bytes(
                        part.get_payload(decode=True),
                        part.get_content_charset(),
                    )
                    body = re.sub(r"<[^>]+>", "", html)
                    body = re.sub(r"\s+", " ", body).strip()
                except Exception:
                    continue
    else:
        try:
            body = _decode_bytes(msg.get_payload(decode=True), msg.get_content_charset())
        except Exception:
            body = str(msg.get_payload())

    return body.strip()


def _get_attachments(msg: email.message.Message) -> list[str]:
    """提取附件文件名列表。"""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append(_decode_header_value(filename))
    return attachments


_IMAGE_MIME_PREFIX = "image/"
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _get_image_attachments(msg: email.message.Message) -> list[dict]:
    """提取邮件中的图片附件二进制数据，仅保留 image/* 类型。

    返回 [{filename, content_type, size, data(bytes)}]
    """
    images: list[dict] = []
    if not msg.is_multipart():
        return images

    for part in msg.walk():
        content_type = (part.get_content_type() or "").lower()
        filename_raw = part.get_filename()
        filename = _decode_header_value(filename_raw) if filename_raw else ""

        is_image = content_type.startswith(_IMAGE_MIME_PREFIX) or (
            filename and filename.lower().endswith(_IMAGE_EXT)
        )
        if not is_image:
            continue

        try:
            data = part.get_payload(decode=True)
        except Exception:
            continue
        if not data:
            continue

        if not filename:
            ext = content_type.split("/", 1)[-1] if "/" in content_type else "bin"
            filename = f"inline_image_{len(images) + 1}.{ext}"

        images.append({
            "filename": filename,
            "content_type": content_type or "image/png",
            "size": len(data),
            "data": data,
        })

    return images


def fetch_emails(
    folder: str = "INBOX",
    limit: int = 200,
    since_date: Optional[str] = None,
    include_image_attachments: bool = False,
) -> list[dict]:
    """
    从 IMAP 邮箱拉取邮件。
    Args:
        folder: 邮箱文件夹，默认 INBOX
        limit: 最多拉取邮件数
        since_date: 起始日期，格式 YYYY-MM-DD
        include_image_attachments: 是否同时载入图片附件二进制（用于 AI 视觉识别）
    """
    host = settings.email_imap_host
    port = settings.email_imap_port
    address = settings.email_address
    password = settings.email_password

    if not address or not password or password == "your_email_password_here":
        raise ValueError("请先在 .env 中配置 EMAIL_ADDRESS 和 EMAIL_PASSWORD")

    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(address, password)

    all_emails = []

    for folder_name in [folder, "Sent Messages", "INBOX.Sent Messages", "已发送"]:
        try:
            status, _ = mail.select(folder_name, readonly=True)
            if status != "OK":
                continue
        except Exception:
            continue

        search_criteria = "ALL"
        if since_date:
            dt = datetime.strptime(since_date, "%Y-%m-%d")
            imap_date = dt.strftime("%d-%b-%Y")
            search_criteria = f"(SINCE {imap_date})"

        status, message_ids = mail.search(None, search_criteria)
        if status != "OK":
            continue

        ids = message_ids[0].split()
        ids = ids[-limit:]

        for msg_id in ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                from_name, from_addr = _decode_email_address(msg.get("From", ""))
                to_raw = msg.get("To", "")
                to_addrs = [_decode_email_address(a.strip())[1] for a in to_raw.split(",")]
                cc_raw = msg.get("Cc", "")
                cc_addrs = [_decode_email_address(a.strip())[1] for a in cc_raw.split(",")] if cc_raw else []
                subject = _decode_header_value(msg.get("Subject", ""))

                date_str = msg.get("Date", "")
                try:
                    date_dt = parsedate_to_datetime(date_str)
                    date_iso = date_dt.isoformat()
                except Exception:
                    date_iso = date_str

                body = _get_email_body(msg)
                attachments = _get_attachments(msg)
                image_attachments = _get_image_attachments(msg) if include_image_attachments else []
                message_id = msg.get("Message-ID", f"imap-{folder_name}-{msg_id.decode()}")

                all_emails.append(
                    {
                        "id": message_id,
                        "from": from_addr,
                        "from_name": from_name,
                        "to": to_addrs,
                        "cc": cc_addrs,
                        "date": date_iso,
                        "subject": subject,
                        "body": body[:5000],
                        "has_attachment": len(attachments) > 0,
                        "attachment_names": attachments,
                        "image_attachments": image_attachments,
                        "folder": folder_name,
                    }
                )
            except Exception as exc:
                print(f"[EmailFetcher] 解析邮件失败 (id={msg_id}): {exc}")
                continue

    mail.logout()

    seen_ids = set()
    unique_emails = []
    for item in all_emails:
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        unique_emails.append(item)

    unique_emails.sort(key=lambda x: x.get("date", ""), reverse=True)
    return unique_emails[:limit]
