# app/routers/front/front_submit.py
# 前台工具提交 API（无需登录）
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.nav import NavSubmission

router = APIRouter(prefix="/api/front/submit", tags=["前台-工具提交"])


# ============ 请求模型 ============

class SubmitRequest(BaseModel):
    name: str
    url: str
    contact_email: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("工具名称不能为空")
        if len(v) > 128:
            raise ValueError("工具名称不能超过128个字符")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("网址不能为空")
        if not (v.startswith("http://") or v.startswith("https://")):
            v = "https://" + v
        if len(v) > 512:
            raise ValueError("网址过长")
        return v

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if "@" not in v or len(v) > 128:
            raise ValueError("邮箱格式不正确")
        return v


# ============ 提交工具 ============

@router.post("")
async def submit_tool(
    data: SubmitRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """前台提交工具网址"""
    # 获取提交者IP
    submitter_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not submitter_ip:
        submitter_ip = request.client.host if request.client else None

    # 防重复：同一URL在24小时内只能提交一次
    cutoff = datetime.now() - timedelta(hours=24)
    existing = db.query(NavSubmission).filter(
        NavSubmission.url == data.url,
        NavSubmission.created_at >= cutoff,
        NavSubmission.status != "rejected"
    ).first()
    if existing:
        return {
            "success": False,
            "message": "该网址在24小时内已提交过，请耐心等待审核",
            "submission_id": existing.id
        }

    # 创建提交记录
    submission = NavSubmission(
        url=data.url,
        submitter_name=data.name,
        contact_email=data.contact_email,
        submitter_ip=submitter_ip,
        status="pending",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    # 后台异步处理：截图 + AI 写作
    background_tasks.add_task(_run_process, submission.id)

    return {
        "success": True,
        "submission_id": submission.id,
        "message": "提交成功！我们正在自动截图和AI分析，审核通常在1-3个工作日内完成。",
    }


@router.get("/status/{submission_id}")
def get_submission_status(submission_id: int, db: Session = Depends(get_db)):
    """查询提交状态（用于前台轮询）"""
    sub = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    return {
        "id": sub.id,
        "url": sub.url,
        "status": sub.status,
        "created_at": sub.created_at,
    }


def _run_process(submission_id: int):
    """在同步上下文中运行异步处理任务"""
    from app.services.snapshot_ai_service import process_submission_async
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_submission_async(submission_id))
    finally:
        loop.close()
