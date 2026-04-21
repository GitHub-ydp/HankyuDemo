"""邮件检索服务：ChromaDB + BGE-M3 向量检索 + Qwen 分析。"""
import hashlib
import json
import os
from typing import Optional
from urllib import error, request

import chromadb

_model = None
_collection = None
_chroma_client = None

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
EMAILS_PATH = os.path.join(DATA_DIR, "emails", "mock_emails.json")
CHROMA_PERSIST_DIR = os.path.join(DATA_DIR, "chroma_db")


def get_model():
    global _model
    if _model is None:
        from FlagEmbedding import BGEM3FlagModel

        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        print("[EmailSearch] BGE-M3 model loaded")
    return _model


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _chroma_client


def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name="emails",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _safe_id(raw_id: str) -> str:
    return hashlib.md5(raw_id.encode()).hexdigest()


def _join_value(value: str | list[str] | None) -> str:
    if isinstance(value, list):
        return ", ".join(item for item in value if item)
    return value or ""


def _email_item_from_source(email: dict, *, content: str = "", score: float = 1.0) -> dict:
    return {
        "id": email.get("id", ""),
        "subject": email.get("subject", ""),
        "from": email.get("from", ""),
        "from_name": email.get("from_name", ""),
        "to": _join_value(email.get("to", "")),
        "date": email.get("date", ""),
        "score": score,
        "content": content or email.get("body", ""),
        "category": email.get("category", ""),
        "tags": _join_value(email.get("tags", "")),
        "has_attachment": str(email.get("has_attachment", False)),
        "folder": email.get("folder", ""),
    }


def load_mock_emails() -> list[dict]:
    with open(EMAILS_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def build_email_text(email: dict) -> str:
    parts = [
        f"Subject: {email.get('subject', '')}",
        f"From: {email.get('from_name', '')} <{email.get('from', '')}>",
        f"To: {_join_value(email.get('to', ''))}",
        f"Date: {email.get('date', '')}",
        f"Body: {email.get('body', '')}",
    ]
    if email.get("tags"):
        parts.append(f"Tags: {_join_value(email.get('tags', ''))}")
    return "\n".join(parts)


def _index_email_list(emails: list[dict], force: bool = False) -> dict:
    collection = get_collection()

    existing_count = collection.count()
    if existing_count > 0 and not force:
        return {"status": "already_indexed", "count": existing_count, "emails": []}

    if force and existing_count > 0:
        client = get_chroma_client()
        client.delete_collection("emails")
        global _collection
        _collection = None
        collection = get_collection()

    if not emails:
        return {"status": "no_emails", "count": 0, "emails": []}

    model = get_model()
    texts = [build_email_text(email) for email in emails]
    embeddings = model.encode(texts, batch_size=8)["dense_vecs"]

    batch_size = 100
    for start in range(0, len(emails), batch_size):
        end = min(start + batch_size, len(emails))
        batch_emails = emails[start:end]
        batch_texts = texts[start:end]
        batch_embeddings = embeddings[start:end]

        collection.add(
            ids=[_safe_id(email["id"]) for email in batch_emails],
            embeddings=[embedding.tolist() for embedding in batch_embeddings],
            documents=batch_texts,
            metadatas=[
                {
                    "id": email.get("id", ""),
                    "from": email.get("from", ""),
                    "from_name": email.get("from_name", ""),
                    "to": _join_value(email.get("to", "")),
                    "date": email.get("date", ""),
                    "subject": email.get("subject", ""),
                    "language": email.get("language", ""),
                    "category": email.get("category", ""),
                    "tags": _join_value(email.get("tags", "")),
                    "has_attachment": str(email.get("has_attachment", False)),
                    "folder": email.get("folder", ""),
                }
                for email in batch_emails
            ],
        )

    indexed_emails = [
        _email_item_from_source(email, content=build_email_text(email))
        for email in sorted(emails, key=lambda item: item.get("date", ""), reverse=True)
    ]
    return {"status": "indexed", "count": len(emails), "emails": indexed_emails}


def index_mock_emails(force: bool = False) -> dict:
    return _index_email_list(load_mock_emails(), force=force)


def index_imap_emails(force: bool = False, limit: int = 200, since_date: Optional[str] = None) -> dict:
    from app.services.email_fetcher import fetch_emails

    emails = fetch_emails(limit=limit, since_date=since_date)
    return _index_email_list(emails, force=force)


def search_emails(
    query: str,
    top_k: int = 10,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []

    model = get_model()
    query_embedding = model.encode([query], batch_size=1)["dense_vecs"][0].tolist()

    where_conditions = []
    if date_from:
        where_conditions.append({"date": {"$gte": date_from}})
    if date_to:
        where_conditions.append({"date": {"$lte": date_to}})

    where = None
    if len(where_conditions) == 1:
        where = where_conditions[0]
    elif len(where_conditions) > 1:
        where = {"$and": where_conditions}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    items = []
    if results and results["ids"] and results["ids"][0]:
        for index, item_id in enumerate(results["ids"][0]):
            metadata = results["metadatas"][0][index]
            items.append(
                {
                    "id": metadata.get("id", item_id),
                    "subject": metadata.get("subject", ""),
                    "from": metadata.get("from", ""),
                    "from_name": metadata.get("from_name", ""),
                    "to": metadata.get("to", ""),
                    "date": metadata.get("date", ""),
                    "category": metadata.get("category", ""),
                    "tags": metadata.get("tags", ""),
                    "has_attachment": metadata.get("has_attachment", "False"),
                    "folder": metadata.get("folder", ""),
                    "score": round(1 - results["distances"][0][index], 4),
                    "content": results["documents"][0][index],
                }
            )

    items.sort(key=lambda item: item.get("date", ""))
    return items


def analyze_emails(query: str, top_k: int = 15) -> dict:
    results = search_emails(query, top_k=top_k)
    if not results:
        return {"query": query, "count": 0, "emails": [], "analysis": "未找到相关邮件。"}

    email_context = ""
    for index, item in enumerate(results, 1):
        email_context += f"\n--- 邮件 {index} ---\n"
        email_context += f"日期: {item['date']}\n"
        email_context += f"发件人: {item['from_name']} <{item['from']}>\n"
        email_context += f"收件人: {item['to']}\n"
        email_context += f"主题: {item['subject']}\n"
        email_context += f"内容:\n{item['content'][:1500]}\n"

    from app.core.config import settings

    if not settings.qwen_api_key:
        analysis = _fallback_analysis(query, results)
    else:
        analysis = _qwen_analysis(query, email_context)

    return {
        "query": query,
        "count": len(results),
        "emails": results,
        "analysis": analysis,
    }


def _qwen_analysis(query: str, email_context: str) -> str:
    from app.core.config import settings

    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": "你是严谨的企业邮件分析助手。"},
            {
                "role": "user",
                "content": f"""你是一位物流行业的邮件分析助手。请根据以下检索到的邮件，围绕用户的查询进行分析。

【用户查询】
{query}

【检索到的相关邮件】
{email_context}

【要求】
1. 按时间线顺序梳理事件脉络
2. 提取关键信息，如金额、航线、费率、客户、决策等
3. 总结当前状态和待办事项，如有
4. 用中文回答，使用 Markdown 格式
""",
            },
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
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

    try:
        with request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen 请求失败: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Qwen 连接失败: {exc.reason}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Qwen 返回为空")

    content = (choices[0].get("message") or {}).get("content", "")
    if not content:
        raise RuntimeError("Qwen 未返回分析内容")
    return content


def _fallback_analysis(query: str, results: list[dict]) -> str:
    lines = [
        "## 邮件检索结果分析",
        "",
        f"**查询**: {query}",
        f"**匹配邮件数**: {len(results)}",
        "",
        "### 时间线",
        "",
    ]

    for item in results:
        date = item["date"][:10] if item.get("date") else "未知日期"
        direction = "收件" if item.get("folder") == "INBOX" else "发件"
        lines.append(f"- **{date}** [{direction}] {item['from_name'] or item['from']}: {item['subject']}")

    people = sorted({item["from_name"] for item in results if item.get("from_name")})
    lines.extend(["", "### 涉及联系人", ""])
    for person in people:
        lines.append(f"- {person}")

    lines.extend(["", "> 提示：配置 QWEN_API_KEY 后可获得通义千问深度分析。"])
    return "\n".join(lines)
