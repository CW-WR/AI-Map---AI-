# app/routers/admin_submission.py
# 后台工具提交审核 API
import json
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.nav import NavSubmission, NavTool, NavCategory, NavTag, NavToolScreenshot
from app.models.user import User

router = APIRouter(prefix="/api/admin/submission", tags=["后台-工具提交审核"])


# ============ 请求模型 ============

class SubmissionUpdate(BaseModel):
    ai_name: Optional[str] = None
    ai_slug: Optional[str] = None
    ai_description: Optional[str] = None
    ai_content: Optional[str] = None
    ai_pricing_type: Optional[str] = None
    ai_features: Optional[List[str]] = None
    logo_url: Optional[str] = None
    screenshots: Optional[List[str]] = None


class ApproveRequest(BaseModel):
    category_id: int
    tag_ids: List[int] = []
    # 可覆盖 AI 内容
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    pricing_type: Optional[str] = None
    features: Optional[List[str]] = None


class RejectRequest(BaseModel):
    admin_note: Optional[str] = None


# ============ 工具函数 ============

def _submission_to_dict(sub: NavSubmission) -> dict:
    screenshots = []
    if sub.screenshots:
        try:
            screenshots = json.loads(sub.screenshots)
        except Exception:
            pass
    features = []
    if sub.ai_features:
        try:
            features = json.loads(sub.ai_features)
        except Exception:
            pass
    return {
        "id": sub.id,
        "url": sub.url,
        "submitter_name": sub.submitter_name,
        "contact_email": sub.contact_email,
        "submitter_ip": sub.submitter_ip,
        "ai_name": sub.ai_name,
        "ai_slug": sub.ai_slug,
        "ai_description": sub.ai_description,
        "ai_content": sub.ai_content,
        "ai_pricing_type": sub.ai_pricing_type,
        "ai_features": features,
        "logo_url": sub.logo_url,
        "screenshots": screenshots,
        "ai_category_id": sub.ai_category_id,
        "ai_tag_ids": [int(x) for x in sub.ai_tag_ids.split(",") if x.strip()] if sub.ai_tag_ids else [],
        "task_log": sub.task_log,
        "status": sub.status,
        "task_error": sub.task_error,
        "tool_id": sub.tool_id,
        "admin_note": sub.admin_note,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
    }


# ============ 接口 ============

@router.get("/list")
def list_submissions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取提交记录列表"""
    query = db.query(NavSubmission)
    if status:
        query = query.filter(NavSubmission.status == status)
    if keyword:
        query = query.filter(NavSubmission.url.contains(keyword))
    total = query.count()
    items = query.order_by(desc(NavSubmission.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "list": [_submission_to_dict(s) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats")
def submission_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """各状态数量统计"""
    statuses = ["pending", "processing", "ready", "approved", "rejected", "failed"]
    result = {}
    for s in statuses:
        result[s] = db.query(NavSubmission).filter(NavSubmission.status == s).count()
    result["total"] = db.query(NavSubmission).count()
    return result


@router.get("/{submission_id}")
def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取提交记录详情"""
    sub = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    return _submission_to_dict(sub)


@router.put("/{submission_id}")
def update_submission(
    submission_id: int,
    data: SubmissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新提交记录中的AI生成内容（管理员可手动修改）"""
    sub = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="提交记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "ai_features":
            setattr(sub, key, json.dumps(value, ensure_ascii=False) if value is not None else None)
        elif key == "screenshots":
            setattr(sub, "screenshots", json.dumps(value, ensure_ascii=False) if value is not None else None)
        else:
            setattr(sub, key, value)

    db.commit()
    db.refresh(sub)
    return _submission_to_dict(sub)


@router.post("/{submission_id}/approve")
def approve_submission(
    submission_id: int,
    data: ApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """审核通过：自动创建 NavTool 并发布"""
    sub = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    if sub.status == "approved":
        raise HTTPException(status_code=400, detail="该提交已审核通过")

    # 验证分类
    category = db.query(NavCategory).filter(NavCategory.id == data.category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="分类不存在")

    # 用请求数据覆盖，否则使用AI生成内容
    name = (data.name or sub.ai_name or "").strip()
    slug = (data.slug or sub.ai_slug or "").strip()
    description = (data.description or sub.ai_description or "").strip()
    content = data.content or sub.ai_content
    pricing_type = data.pricing_type or sub.ai_pricing_type or "免费"

    if not name:
        raise HTTPException(status_code=400, detail="工具名称不能为空")
    if not slug:
        raise HTTPException(status_code=400, detail="URL标识不能为空")
    if not description:
        raise HTTPException(status_code=400, detail="工具简介不能为空")

    # 检查 slug 重复
    if db.query(NavTool).filter(NavTool.slug == slug).first():
        # 自动加后缀避免冲突
        slug = f"{slug}-{submission_id}"

    # 处理功能列表
    if data.features is not None:
        features_json = json.dumps(data.features, ensure_ascii=False)
    elif sub.ai_features:
        features_json = sub.ai_features
    else:
        features_json = None

    # 处理截图列表
    screenshots_list = []
    if sub.screenshots:
        try:
            screenshots_list = json.loads(sub.screenshots)
        except Exception:
            pass

    # 创建工具
    tool = NavTool(
        name=name,
        slug=slug,
        description=description,
        content=content,
        icon=sub.logo_url,
        cover=screenshots_list[0] if screenshots_list else None,
        url=sub.url,
        category_id=data.category_id,
        pricing_type=pricing_type,
        features=features_json,
        status=1,
        is_recommended=False,
    )
    db.add(tool)
    db.flush()

    # 关联标签
    if data.tag_ids:
        tags = db.query(NavTag).filter(NavTag.id.in_(data.tag_ids)).all()
        tool.tags = tags

    # 写入截图
    for idx, img_url in enumerate(screenshots_list):
        if img_url:
            screenshot = NavToolScreenshot(tool_id=tool.id, image_url=img_url, sort=idx)
            db.add(screenshot)

    # 更新提交记录状态
    sub.status = "approved"
    sub.tool_id = tool.id
    db.commit()

    return {
        "success": True,
        "message": "审核通过，工具已发布",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
    }


@router.post("/{submission_id}/reject")
def reject_submission(
    submission_id: int,
    data: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """拒绝提交"""
    sub = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    sub.status = "rejected"
    sub.admin_note = data.admin_note
    db.commit()
    return {"success": True, "message": "已拒绝"}


@router.post("/{submission_id}/retry")
def retry_submission(
    submission_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重新触发截图+AI任务（处理失败时使用）"""
    sub = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    if sub.status not in ("failed", "pending"):
        raise HTTPException(status_code=400, detail="只有失败或待处理的记录才能重试")

    sub.status = "pending"
    sub.task_error = None
    db.commit()

    background_tasks.add_task(_run_process, submission_id)
    return {"success": True, "message": "已重新触发处理任务"}


@router.delete("/{submission_id}")
def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除提交记录"""
    sub = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    db.delete(sub)
    db.commit()
    return {"success": True}


def _run_process(submission_id: int):
    """在同步上下文中运行异步处理任务"""
    from app.services.snapshot_ai_service import process_submission_async
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_submission_async(submission_id))
    finally:
        loop.close()


# ============ 手动采集每日AI工具 ============

class FetchDailyRequest(BaseModel):
    date: str  # YYYY-MM-DD


@router.post("/fetch-daily")
def fetch_daily_tools_api(
    data: FetchDailyRequest,
    current_user: User = Depends(get_current_user),
):
    """手动采集指定日期的AI工具，同步执行并返回结果"""
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", data.date):
        raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD")

    try:
        from app.tasks.daily_tools import fetch_daily_tools
        result = fetch_daily_tools(data.date)
        return {"success": True, "message": result}
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"采集失败：{str(e)}\n{error_detail[-500:]}")

