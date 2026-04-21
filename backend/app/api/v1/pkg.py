"""PKG（入札包）解析与自动填入 API"""
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.services.pkg_parser import parse_pkg, parse_result_to_dict
from app.services.pkg_filler import fill_pkg, fill_summary_to_dict
from app.services.rate_db import get_all_rates

router = APIRouter(prefix="/pkg", tags=["PKG入札包"])

# 存储会话状态（Demo 用，生产环境应用 Redis/DB）
_sessions: dict[str, dict] = {}


@router.post("/upload")
async def upload_and_parse(file: UploadFile = File(...)):
    """上传入札包 Excel 并解析结构

    Returns:
        session_id: 会话ID，用于后续填入操作
        parse_result: 解析结果（段、航线列表）
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, '仅支持 Excel 文件 (.xlsx/.xls)')

    # 保存上传文件
    session_id = str(uuid.uuid4())[:8]
    upload_dir = Path(settings.upload_dir) / 'pkg' / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    input_path = upload_dir / file.filename
    content = await file.read()
    with open(input_path, 'wb') as f:
        f.write(content)

    # 解析
    try:
        result = parse_pkg(input_path)
    except Exception as e:
        raise HTTPException(400, f'Excel 解析失败: {str(e)}')

    # 保存会话
    _sessions[session_id] = {
        'input_path': str(input_path),
        'filename': file.filename,
        'parse_result': result,
    }

    return {
        'code': 0,
        'message': 'PKG 解析成功',
        'data': {
            'session_id': session_id,
            'parse_result': parse_result_to_dict(result),
        },
    }


@router.post("/fill/{session_id}")
async def auto_fill(
    session_id: str,
    overwrite: bool = Query(False, description="是否覆盖已有数据"),
):
    """自动填入费率数据

    Args:
        session_id: 上传时返回的会话ID
        overwrite: 是否覆盖已有值
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, '会话不存在或已过期，请重新上传')

    input_path = Path(session['input_path'])
    output_path = input_path.parent / f"filled_{session['filename']}"

    try:
        summary = fill_pkg(
            session['parse_result'],
            input_path,
            output_path,
            overwrite_existing=overwrite,
        )
    except Exception as e:
        raise HTTPException(500, f'自动填入失败: {str(e)}')

    # 更新会话
    session['output_path'] = str(output_path)
    session['fill_summary'] = summary

    return {
        'code': 0,
        'message': f'自动填入完成: {summary.filled_count}/{summary.total_lanes} 条航线已填入',
        'data': fill_summary_to_dict(summary),
    }


@router.get("/download/{session_id}")
async def download_filled(session_id: str):
    """下载填入完成的 Excel 文件"""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, '会话不存在或已过期')

    output_path = session.get('output_path')
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(404, '尚未执行自动填入，请先调用 /fill 接口')

    filename = f"filled_{session['filename']}"
    return FileResponse(
        output_path,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=filename,
    )


@router.get("/rates")
async def list_rates():
    """查看当前费率数据库中的所有费率（Demo 用）"""
    rates = get_all_rates()
    return {
        'code': 0,
        'message': f'共 {len(rates)} 条费率',
        'data': rates,
    }


@router.get("/sessions")
async def list_sessions():
    """查看当前所有活跃会话（Debug 用）"""
    return {
        'code': 0,
        'data': {
            sid: {
                'filename': s['filename'],
                'has_output': 'output_path' in s,
            }
            for sid, s in _sessions.items()
        },
    }
