"""邮件检索 API 路由"""
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.services.email_report_service import generate_report_html
from app.services.email_search_service import (
    analyze_emails,
    index_imap_emails,
    index_mock_emails,
    search_emails,
)

router = APIRouter(prefix="/emails", tags=["邮件检索"])


@router.post("/index/mock")
def api_index_mock(force: bool = Query(False, description="是否强制重建索引")):
    """从模拟数据建立索引（Demo 用）"""
    return index_mock_emails(force=force)


@router.post("/index/imap")
def api_index_imap(
    force: bool = Query(False, description="是否强制重建索引"),
    limit: int = Query(200, ge=1, le=1000, description="最多拉取邮件数"),
    since_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
):
    """从真实邮箱(IMAP)拉取邮件并建立索引"""
    return index_imap_emails(force=force, limit=limit, since_date=since_date)


@router.get("/search")
def api_search(
    q: str = Query(..., description="搜索内容（支持中日英跨语言）"),
    top_k: int = Query(10, ge=1, le=50, description="返回结果数量"),
    date_from: Optional[str] = Query(None, description="起始日期"),
    date_to: Optional[str] = Query(None, description="截止日期"),
):
    """语义搜索邮件"""
    results = search_emails(query=q, top_k=top_k, date_from=date_from, date_to=date_to)
    return {"query": q, "count": len(results), "results": results}


@router.get("/analyze")
def api_analyze(
    q: str = Query(..., description="分析指令，如：检索和丰田相关的邮件，按时间线汇总"),
    top_k: int = Query(15, ge=1, le=50, description="检索邮件数"),
):
    """
    核心演示接口：AI 邮件分析

    示例查询：
    - 检索和丰田汽车相关的所有往来邮件，按时间线汇总
    - 近期有哪些运价变动通知？影响了哪些客户？
    - 三菱电机的入札进展如何？
    """
    return analyze_emails(query=q, top_k=top_k)


@router.get("/report")
def api_report(
    q: str = Query(..., description="分析指令，将基于相关邮件生成 HTML 脉络报告"),
    top_k: int = Query(15, ge=1, le=50, description="检索邮件数"),
):
    """
    生成并导出多封邮件的脉络分析 HTML 报告（可直接下载保存）。
    """
    result = generate_report_html(query=q, top_k=top_k)
    filename_ascii = "email_report.html"
    filename_utf8 = quote(result["filename"])
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{filename_utf8}"
        ),
        "X-Email-Count": str(result["count"]),
    }
    return Response(
        content=result["html"],
        media_type="text/html; charset=utf-8",
        headers=headers,
    )
