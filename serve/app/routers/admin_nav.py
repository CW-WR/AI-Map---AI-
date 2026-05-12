# app/routers/admin_nav.py
# 后台导航管理API
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from typing import List, Optional
from pydantic import BaseModel, Field
import json

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.nav import NavCategory, NavTool, NavTag, NavToolTag, NavToolScreenshot, NavClickLog, NavPage, NavMenu, NavFriendlyLink, NavArticle, NavArticleCategory, NavSubmission
from app.models.user import User
from app.models.login_log import LoginLog

router = APIRouter(prefix="/api/admin/nav", tags=["后台-导航管理"])


# ============ 请求/响应模型 ============

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    slug: str = Field(..., min_length=1, max_length=64)
    icon: Optional[str] = None
    description: Optional[str] = None
    sort: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    slug: Optional[str] = Field(None, min_length=1, max_length=64)
    icon: Optional[str] = None
    description: Optional[str] = None
    sort: Optional[int] = None
    status: Optional[int] = None


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)
    slug: str = Field(..., min_length=1, max_length=32)
    sort: int = 0


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=32)
    slug: Optional[str] = Field(None, min_length=1, max_length=32)
    sort: Optional[int] = None
    status: Optional[int] = None


class ScreenshotItem(BaseModel):
    url: str
    sort: int = 0

class ToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    content: Optional[str] = None
    icon: Optional[str] = None
    cover: Optional[str] = None
    url: str = Field(..., min_length=1, max_length=512)
    category_id: int
    pricing_type: Optional[str] = None
    pricing_desc: Optional[str] = None
    features: List[str] = []
    tag_ids: List[int] = []
    screenshots: List[ScreenshotItem] = []
    seo_title: Optional[str] = None
    seo_desc: Optional[str] = None
    is_recommended: bool = False
    sort: int = 0


class ToolUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    slug: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, min_length=1)
    content: Optional[str] = None
    icon: Optional[str] = None
    cover: Optional[str] = None
    url: Optional[str] = Field(None, min_length=1, max_length=512)
    category_id: Optional[int] = None
    pricing_type: Optional[str] = None
    pricing_desc: Optional[str] = None
    features: Optional[List[str]] = None
    tag_ids: Optional[List[int]] = None
    screenshots: Optional[List[ScreenshotItem]] = None
    seo_title: Optional[str] = None
    seo_desc: Optional[str] = None
    is_recommended: Optional[bool] = None
    status: Optional[int] = None
    sort: Optional[int] = None


# ============ 分类管理接口 ============

@router.get("/categories")
def admin_get_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取分类列表（后台）"""
    query = db.query(NavCategory)
    
    if keyword:
        query = query.filter(
            NavCategory.name.contains(keyword) | 
            NavCategory.slug.contains(keyword)
        )
    
    total = query.count()
    categories = query.order_by(NavCategory.sort.asc()).offset((page - 1) * page_size).limit(page_size).all()
    
    # 获取每个分类的工具数量
    result = []
    for cat in categories:
        tool_count = db.query(NavTool).filter(NavTool.category_id == cat.id).count()
        result.append({
            "id": cat.id,
            "name": cat.name,
            "slug": cat.slug,
            "icon": cat.icon,
            "description": cat.description,
            "sort": cat.sort,
            "status": cat.status,
            "tool_count": tool_count,
            "created_at": cat.created_at,
            "updated_at": cat.updated_at
        })
    
    return {
        "list": result,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/categories")
def admin_create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建分类"""
    # 检查slug是否已存在
    if db.query(NavCategory).filter(NavCategory.slug == data.slug).first():
        raise HTTPException(status_code=400, detail="分类标识已存在")
    
    category = NavCategory(**data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/categories/{id}")
def admin_update_category(
    id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新分类"""
    category = db.query(NavCategory).filter(NavCategory.id == id).first()
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    
    # 检查slug是否被其他分类使用
    if data.slug and data.slug != category.slug:
        if db.query(NavCategory).filter(NavCategory.slug == data.slug, NavCategory.id != id).first():
            raise HTTPException(status_code=400, detail="分类标识已存在")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{id}")
def admin_delete_category(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除分类"""
    category = db.query(NavCategory).filter(NavCategory.id == id).first()
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    
    # 检查是否有关联的工具
    tool_count = db.query(NavTool).filter(NavTool.category_id == id).count()
    if tool_count > 0:
        raise HTTPException(status_code=400, detail="该分类下存在工具，无法删除")
    
    db.delete(category)
    db.commit()
    return {"success": True}


# ============ 工具管理接口 ============

@router.get("/tools")
def admin_get_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取工具列表（后台）"""
    query = db.query(NavTool).options(joinedload(NavTool.category))
    
    if keyword:
        query = query.filter(
            NavTool.name.contains(keyword) | 
            NavTool.description.contains(keyword)
        )
    
    if category_id:
        query = query.filter(NavTool.category_id == category_id)
    
    if status is not None:
        query = query.filter(NavTool.status == status)
    
    total = query.count()
    tools = query.order_by(desc(NavTool.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for tool in tools:
        result.append({
            "id": tool.id,
            "name": tool.name,
            "slug": tool.slug,
            "description": tool.description,
            "icon": tool.icon,
            "cover": tool.cover,
            "url": tool.url,
            "category_id": tool.category_id,
            "category_name": tool.category.name if tool.category else "",
            "pricing_type": tool.pricing_type,
            "views": tool.views,
            "clicks": tool.clicks,
            "hot": tool.hot,
            "is_recommended": tool.is_recommended,
            "status": tool.status,
            "sort": tool.sort,
            "created_at": tool.created_at,
            "updated_at": tool.updated_at
        })
    
    return {
        "list": result,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/tools/{id}")
def admin_get_tool_detail(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取工具详情（后台）"""
    tool = db.query(NavTool).options(
        joinedload(NavTool.category),
        joinedload(NavTool.tags),
        joinedload(NavTool.screenshots)
    ).filter(NavTool.id == id).first()
    
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    
    features = []
    if tool.features:
        try:
            features = json.loads(tool.features)
        except:
            features = []
    
    return {
        "id": tool.id,
        "name": tool.name,
        "slug": tool.slug,
        "description": tool.description,
        "content": tool.content,
        "icon": tool.icon,
        "cover": tool.cover,
        "url": tool.url,
        "category_id": tool.category_id,
        "category_name": tool.category.name if tool.category else "",
        "pricing_type": tool.pricing_type,
        "pricing_desc": tool.pricing_desc,
        "features": features,
        "tags": [{"id": t.id, "name": t.name} for t in tool.tags],
        "tag_ids": [t.id for t in tool.tags],
        "screenshots": [{"url": s.image_url, "sort": s.sort} for s in sorted(tool.screenshots, key=lambda x: x.sort)],
        "seo_title": tool.seo_title,
        "seo_desc": tool.seo_desc,
        "views": tool.views,
        "clicks": tool.clicks,
        "likes": tool.likes,
        "hot": tool.hot,
        "is_recommended": tool.is_recommended,
        "status": tool.status,
        "sort": tool.sort,
        "created_at": tool.created_at,
        "updated_at": tool.updated_at
    }


@router.post("/tools")
def admin_create_tool(
    data: ToolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建工具"""
    # 检查slug是否已存在
    if db.query(NavTool).filter(NavTool.slug == data.slug).first():
        raise HTTPException(status_code=400, detail="工具标识已存在")
    
    # 检查分类是否存在
    category = db.query(NavCategory).filter(NavCategory.id == data.category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="分类不存在")
    
    tool_data = data.model_dump(exclude={'tag_ids', 'screenshots', 'features'})
    tool_data['features'] = json.dumps(data.features) if data.features else None
    
    tool = NavTool(**tool_data)
    db.add(tool)
    db.flush()
    
    # 关联标签
    if data.tag_ids:
        tags = db.query(NavTag).filter(NavTag.id.in_(data.tag_ids)).all()
        tool.tags = tags
    
    # 添加截图
    if data.screenshots:
        for item in data.screenshots:
            screenshot = NavToolScreenshot(tool_id=tool.id, image_url=item.url, sort=item.sort)
            db.add(screenshot)
    
    db.commit()
    db.refresh(tool)
    return tool


@router.put("/tools/{id}")
def admin_update_tool(
    id: int,
    data: ToolUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新工具"""
    tool = db.query(NavTool).filter(NavTool.id == id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    
    # 检查slug是否被其他工具使用
    if data.slug and data.slug != tool.slug:
        if db.query(NavTool).filter(NavTool.slug == data.slug, NavTool.id != id).first():
            raise HTTPException(status_code=400, detail="工具标识已存在")
    
    # 更新基本字段
    update_data = data.model_dump(exclude={'tag_ids', 'screenshots', 'features'}, exclude_unset=True)
    
    if data.features is not None:
        update_data['features'] = json.dumps(data.features)
    
    for key, value in update_data.items():
        setattr(tool, key, value)
    
    # 更新标签关联
    if data.tag_ids is not None:
        if data.tag_ids:
            tags = db.query(NavTag).filter(NavTag.id.in_(data.tag_ids)).all()
            tool.tags = tags
        else:
            # 清空标签关联
            tool.tags = []
    
    # 更新截图
    if data.screenshots is not None:
        # 删除旧截图
        db.query(NavToolScreenshot).filter(NavToolScreenshot.tool_id == id).delete()
        # 添加新截图
        for item in data.screenshots:
            screenshot = NavToolScreenshot(tool_id=id, image_url=item.url, sort=item.sort)
            db.add(screenshot)
    
    db.commit()
    db.refresh(tool)
    return tool


@router.delete("/tools/{id}")
def admin_delete_tool(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除工具"""
    tool = db.query(NavTool).filter(NavTool.id == id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    
    db.delete(tool)
    db.commit()
    return {"success": True}


# ============ 标签管理接口 ============

@router.get("/tags")
def admin_get_tags(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取标签列表（后台）"""
    query = db.query(NavTag)
    total = query.count()
    tags = query.order_by(NavTag.sort.asc()).offset((page - 1) * page_size).limit(page_size).all()
    
    # 获取每个标签的工具数量
    result = []
    for tag in tags:
        tool_count = db.query(NavToolTag).filter(NavToolTag.tag_id == tag.id).count()
        result.append({
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "sort": tag.sort,
            "status": tag.status,
            "tool_count": tool_count,
            "created_at": tag.created_at
        })
    
    return {
        "list": result,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/tags")
def admin_create_tag(
    data: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建标签"""
    if db.query(NavTag).filter(NavTag.slug == data.slug).first():
        raise HTTPException(status_code=400, detail="标签标识已存在")
    
    tag = NavTag(**data.model_dump())
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.put("/tags/{id}")
def admin_update_tag(
    id: int,
    data: TagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新标签"""
    tag = db.query(NavTag).filter(NavTag.id == id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    
    if data.slug and data.slug != tag.slug:
        if db.query(NavTag).filter(NavTag.slug == data.slug, NavTag.id != id).first():
            raise HTTPException(status_code=400, detail="标签标识已存在")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{id}")
def admin_delete_tag(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除标签"""
    tag = db.query(NavTag).filter(NavTag.id == id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    
    db.delete(tag)
    db.commit()
    return {"success": True}


# ============ 数据统计接口 ============

@router.get("/stats")
def admin_get_stats(
    days: int = Query(7, description="趋势天数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Dashboard统计数据"""
    from datetime import datetime, timedelta

    # ---- KPI 指标 ----
    total_tools = db.query(NavTool).count()
    active_tools = db.query(NavTool).filter(NavTool.status == 1).count()
    total_articles = db.query(NavArticle).count()
    published_articles = db.query(NavArticle).filter(NavArticle.status == 1).count()
    total_views = db.query(func.sum(NavTool.views)).scalar() or 0
    total_clicks = db.query(func.sum(NavTool.clicks)).scalar() or 0
    total_submissions = db.query(NavSubmission).count()
    pending_submissions = db.query(NavSubmission).filter(NavSubmission.status.in_(["pending", "processing", "ready"])).count()
    total_categories = db.query(NavCategory).filter(NavCategory.status == 1).count()
    total_tags = db.query(NavTag).filter(NavTag.status == 1).count()

    # 昨日新增对比
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    tools_today = db.query(NavTool).filter(NavTool.created_at >= today).count()
    tools_yesterday = db.query(NavTool).filter(NavTool.created_at >= yesterday, NavTool.created_at < today).count()
    articles_today = db.query(NavArticle).filter(NavArticle.created_at >= today).count()
    articles_yesterday = db.query(NavArticle).filter(NavArticle.created_at >= yesterday, NavArticle.created_at < today).count()

    # ---- 增长趋势 (最近N天) ----
    start_date = today - timedelta(days=days - 1)
    tool_trend = db.query(
        func.date(NavTool.created_at).label("date"),
        func.count().label("count")
    ).filter(NavTool.created_at >= start_date).group_by(func.date(NavTool.created_at)).all()
    tool_trend_map = {str(r.date): r.count for r in tool_trend}

    article_trend = db.query(
        func.date(NavArticle.created_at).label("date"),
        func.count().label("count")
    ).filter(NavArticle.created_at >= start_date).group_by(func.date(NavArticle.created_at)).all()
    article_trend_map = {str(r.date): r.count for r in article_trend}

    trend_labels = []
    trend_tools = []
    trend_articles = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        trend_labels.append(d.strftime("%m-%d"))
        trend_tools.append(tool_trend_map.get(ds, 0))
        trend_articles.append(article_trend_map.get(ds, 0))

    # ---- 工具分类分布 ----
    cat_dist = db.query(
        NavCategory.name,
        func.count(NavTool.id).label("count")
    ).outerjoin(NavTool, NavTool.category_id == NavCategory.id).filter(
        NavCategory.status == 1
    ).group_by(NavCategory.id, NavCategory.name).order_by(desc("count")).all()

    # ---- 资讯分类分布 ----
    article_cat_dist = db.query(
        NavArticleCategory.name,
        func.count(NavArticle.id).label("count")
    ).outerjoin(NavArticle, NavArticle.category_id == NavArticleCategory.id).filter(
        NavArticleCategory.status == 1
    ).group_by(NavArticleCategory.id, NavArticleCategory.name).order_by(desc("count")).all()

    # ---- 提交状态分布 ----
    sub_dist = db.query(
        NavSubmission.status,
        func.count().label("count")
    ).group_by(NavSubmission.status).all()
    submission_status_map = {
        "pending": "待处理", "processing": "处理中", "ready": "待审核",
        "approved": "已通过", "rejected": "已拒绝", "failed": "失败"
    }

    # ---- 热门工具 TOP10 ----
    hot_tools = db.query(NavTool).options(
        joinedload(NavTool.category)
    ).filter(
        NavTool.status == 1
    ).order_by(desc(NavTool.views)).limit(10).all()

    # ---- 最近资讯 ----
    recent_articles = db.query(NavArticle).options(
        joinedload(NavArticle.category)
    ).order_by(desc(NavArticle.created_at)).limit(10).all()

    return {
        "kpi": {
            "total_tools": total_tools,
            "active_tools": active_tools,
            "total_articles": total_articles,
            "published_articles": published_articles,
            "total_views": int(total_views),
            "total_clicks": int(total_clicks),
            "total_submissions": total_submissions,
            "pending_submissions": pending_submissions,
            "total_categories": total_categories,
            "total_tags": total_tags,
            "tools_today": tools_today,
            "tools_yesterday": tools_yesterday,
            "articles_today": articles_today,
            "articles_yesterday": articles_yesterday,
        },
        "trend": {
            "labels": trend_labels,
            "tools": trend_tools,
            "articles": trend_articles,
        },
        "category_dist": [
            {"name": r.name, "value": r.count} for r in cat_dist
        ],
        "article_cat_dist": [
            {"name": r.name, "value": r.count} for r in article_cat_dist
        ],
        "submission_dist": [
            {"name": submission_status_map.get(r.status, r.status), "value": r.count} for r in sub_dist
        ],
        "hot_tools": [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category.name if t.category else "-",
                "views": t.views,
                "clicks": t.clicks,
                "hot": t.hot
            } for t in hot_tools
        ],
        "recent_articles": [
            {
                "id": a.id,
                "title": a.title,
                "category": a.category.name if a.category else "-",
                "views": a.views,
                "status": "已发布" if a.status == 1 else "草稿",
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "-"
            } for a in recent_articles
        ]
    }


# ============ 静态页面管理 ============

class PageCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=64)
    content: Optional[str] = None
    meta_desc: Optional[str] = None
    status: int = 1
    sort: int = 0


class PageUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=128)
    slug: Optional[str] = Field(None, min_length=1, max_length=64)
    content: Optional[str] = None
    meta_desc: Optional[str] = None
    status: Optional[int] = None
    sort: Optional[int] = None


@router.get("/pages")
def list_pages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取所有静态页面"""
    pages = db.query(NavPage).order_by(NavPage.sort, NavPage.id).all()
    return [{
        "id": p.id,
        "title": p.title,
        "slug": p.slug,
        "meta_desc": p.meta_desc,
        "status": p.status,
        "sort": p.sort,
        "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M") if p.updated_at else ""
    } for p in pages]


@router.get("/pages/{page_id}")
def get_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单个页面详情（含内容）"""
    page = db.query(NavPage).filter(NavPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    return {
        "id": page.id,
        "title": page.title,
        "slug": page.slug,
        "content": page.content,
        "meta_desc": page.meta_desc,
        "status": page.status,
        "sort": page.sort
    }


@router.post("/pages")
def create_page(
    data: PageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建静态页面"""
    if db.query(NavPage).filter(NavPage.slug == data.slug).first():
        raise HTTPException(status_code=400, detail="slug 已存在")
    page = NavPage(**data.model_dump())
    db.add(page)
    db.commit()
    db.refresh(page)
    return {"id": page.id, "message": "创建成功"}


@router.put("/pages/{page_id}")
def update_page(
    page_id: int,
    data: PageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新静态页面"""
    page = db.query(NavPage).filter(NavPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(page, k, v)
    db.commit()
    return {"message": "更新成功"}


@router.delete("/pages/{page_id}")
def delete_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除静态页面"""
    page = db.query(NavPage).filter(NavPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    db.delete(page)
    db.commit()
    return {"message": "删除成功"}


# ============ 导航菜单管理 ============

class MenuCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=64)
    url: str = Field(..., min_length=1, max_length=255)
    menu_type: str = "header"  # header / footer
    open_new_tab: int = 0
    sort: int = 0
    status: int = 1

class MenuUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    menu_type: Optional[str] = None
    open_new_tab: Optional[int] = None
    sort: Optional[int] = None
    status: Optional[int] = None

@router.get("/menus")
def list_menus(
    menu_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(NavMenu)
    if menu_type:
        q = q.filter(NavMenu.menu_type == menu_type)
    menus = q.order_by(NavMenu.sort, NavMenu.id).all()
    return [{
        "id": m.id, "title": m.title, "url": m.url,
        "menu_type": m.menu_type, "open_new_tab": m.open_new_tab,
        "sort": m.sort, "status": m.status
    } for m in menus]

@router.post("/menus")
def create_menu(data: MenuCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    menu = NavMenu(**data.model_dump())
    db.add(menu); db.commit(); db.refresh(menu)
    return {"id": menu.id, "message": "创建成功"}

@router.put("/menus/{menu_id}")
def update_menu(menu_id: int, data: MenuUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    menu = db.query(NavMenu).filter(NavMenu.id == menu_id).first()
    if not menu: raise HTTPException(status_code=404, detail="菜单不存在")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(menu, k, v)
    db.commit()
    return {"message": "更新成功"}

@router.delete("/menus/{menu_id}")
def delete_menu(menu_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    menu = db.query(NavMenu).filter(NavMenu.id == menu_id).first()
    if not menu: raise HTTPException(status_code=404, detail="菜单不存在")
    db.delete(menu); db.commit()
    return {"message": "删除成功"}


# ============ 友情链接管理 ============

class LinkCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    url: str = Field(..., min_length=1, max_length=255)
    logo: Optional[str] = None
    sort: int = 0
    status: int = 1

class LinkUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    logo: Optional[str] = None
    sort: Optional[int] = None
    status: Optional[int] = None

@router.get("/links")
def list_links(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    links = db.query(NavFriendlyLink).order_by(NavFriendlyLink.sort, NavFriendlyLink.id).all()
    return [{
        "id": l.id, "name": l.name, "url": l.url,
        "logo": l.logo, "sort": l.sort, "status": l.status
    } for l in links]

@router.post("/links")
def create_link(data: LinkCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = NavFriendlyLink(**data.model_dump())
    db.add(link); db.commit(); db.refresh(link)
    return {"id": link.id, "message": "创建成功"}

@router.put("/links/{link_id}")
def update_link(link_id: int, data: LinkUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = db.query(NavFriendlyLink).filter(NavFriendlyLink.id == link_id).first()
    if not link: raise HTTPException(status_code=404, detail="友链不存在")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(link, k, v)
    db.commit()
    return {"message": "更新成功"}

@router.delete("/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = db.query(NavFriendlyLink).filter(NavFriendlyLink.id == link_id).first()
    if not link: raise HTTPException(status_code=404, detail="友链不存在")
    db.delete(link); db.commit()
    return {"message": "删除成功"}


# ============ 资讯分类管理 ============

class ArticleCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    slug: str = Field(..., min_length=1, max_length=64)
    icon: Optional[str] = None
    sort: int = 0
    status: int = 1

class ArticleCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    slug: Optional[str] = Field(None, min_length=1, max_length=64)
    icon: Optional[str] = None
    sort: Optional[int] = None
    status: Optional[int] = None

@router.get("/article-categories")
def admin_get_article_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取资讯分类列表"""
    cats = db.query(NavArticleCategory).order_by(NavArticleCategory.sort, NavArticleCategory.id).all()
    result = []
    for c in cats:
        article_count = db.query(NavArticle).filter(NavArticle.category_id == c.id).count()
        result.append({
            "id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon,
            "sort": c.sort, "status": c.status, "article_count": article_count,
            "created_at": c.created_at
        })
    return result

@router.post("/article-categories")
def admin_create_article_category(
    data: ArticleCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if db.query(NavArticleCategory).filter(NavArticleCategory.slug == data.slug).first():
        raise HTTPException(status_code=400, detail="分类标识已存在")
    cat = NavArticleCategory(**data.model_dump())
    db.add(cat); db.commit(); db.refresh(cat)
    return {"id": cat.id, "message": "创建成功"}

@router.put("/article-categories/{cat_id}")
def admin_update_article_category(
    cat_id: int, data: ArticleCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cat = db.query(NavArticleCategory).filter(NavArticleCategory.id == cat_id).first()
    if not cat: raise HTTPException(status_code=404, detail="分类不存在")
    if data.slug and data.slug != cat.slug:
        if db.query(NavArticleCategory).filter(NavArticleCategory.slug == data.slug, NavArticleCategory.id != cat_id).first():
            raise HTTPException(status_code=400, detail="分类标识已存在")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(cat, k, v)
    db.commit()
    return {"message": "更新成功"}

@router.delete("/article-categories/{cat_id}")
def admin_delete_article_category(
    cat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cat = db.query(NavArticleCategory).filter(NavArticleCategory.id == cat_id).first()
    if not cat: raise HTTPException(status_code=404, detail="分类不存在")
    count = db.query(NavArticle).filter(NavArticle.category_id == cat_id).count()
    if count > 0:
        raise HTTPException(status_code=400, detail="该分类下存在资讯，无法删除")
    db.delete(cat); db.commit()
    return {"message": "删除成功"}


# ============ 资讯管理 ============

class ArticleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=200)
    summary: Optional[str] = None
    content: Optional[str] = None
    cover: Optional[str] = None
    category_id: Optional[int] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    author: Optional[str] = None
    is_top: int = 0
    status: int = 0
    sort: int = 0
    published_at: Optional[str] = None


class ArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=1, max_length=200)
    summary: Optional[str] = None
    content: Optional[str] = None
    cover: Optional[str] = None
    category_id: Optional[int] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    author: Optional[str] = None
    is_top: Optional[int] = None
    status: Optional[int] = None
    sort: Optional[int] = None
    published_at: Optional[str] = None


@router.get("/articles")
def admin_get_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    status: Optional[int] = None,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取资讯列表（后台）"""
    query = db.query(NavArticle).options(joinedload(NavArticle.category))

    if keyword:
        query = query.filter(
            NavArticle.title.contains(keyword) |
            NavArticle.summary.contains(keyword)
        )

    if status is not None:
        query = query.filter(NavArticle.status == status)

    if category_id is not None:
        query = query.filter(NavArticle.category_id == category_id)

    total = query.count()
    articles = query.order_by(desc(NavArticle.is_top), desc(NavArticle.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "list": [{
            "id": a.id,
            "title": a.title,
            "slug": a.slug,
            "summary": a.summary,
            "cover": a.cover,
            "category_id": a.category_id,
            "category_name": a.category.name if a.category else None,
            "source": a.source,
            "author": a.author,
            "views": a.views,
            "is_top": a.is_top,
            "status": a.status,
            "sort": a.sort,
            "published_at": a.published_at.strftime("%Y-%m-%d %H:%M") if a.published_at else None,
            "created_at": a.created_at,
            "updated_at": a.updated_at
        } for a in articles],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/articles/{id}")
def admin_get_article(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取资讯详情（后台）"""
    article = db.query(NavArticle).filter(NavArticle.id == id).first()
    if not article:
        raise HTTPException(status_code=404, detail="资讯不存在")
    return {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "summary": article.summary,
        "content": article.content,
        "cover": article.cover,
        "category_id": article.category_id,
        "source": article.source,
        "source_url": article.source_url,
        "author": article.author,
        "views": article.views,
        "is_top": article.is_top,
        "status": article.status,
        "sort": article.sort,
        "published_at": article.published_at.strftime("%Y-%m-%d %H:%M") if article.published_at else None
    }


@router.post("/articles")
def admin_create_article(
    data: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建资讯"""
    if db.query(NavArticle).filter(NavArticle.slug == data.slug).first():
        raise HTTPException(status_code=400, detail="资讯标识已存在")

    from datetime import datetime as dt
    article_data = data.model_dump()
    if article_data.get("published_at"):
        article_data["published_at"] = dt.strptime(article_data["published_at"], "%Y-%m-%d %H:%M")
    else:
        article_data["published_at"] = None

    article = NavArticle(**article_data)
    db.add(article)
    db.commit()
    db.refresh(article)
    return {"id": article.id, "message": "创建成功"}


@router.put("/articles/{id}")
def admin_update_article(
    id: int,
    data: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新资讯"""
    article = db.query(NavArticle).filter(NavArticle.id == id).first()
    if not article:
        raise HTTPException(status_code=404, detail="资讯不存在")

    if data.slug and data.slug != article.slug:
        if db.query(NavArticle).filter(NavArticle.slug == data.slug, NavArticle.id != id).first():
            raise HTTPException(status_code=400, detail="资讯标识已存在")

    from datetime import datetime as dt
    update_data = data.model_dump(exclude_unset=True)
    if "published_at" in update_data:
        if update_data["published_at"]:
            update_data["published_at"] = dt.strptime(update_data["published_at"], "%Y-%m-%d %H:%M")
        else:
            update_data["published_at"] = None

    for key, value in update_data.items():
        setattr(article, key, value)

    db.commit()
    db.refresh(article)
    return {"message": "更新成功"}


@router.delete("/articles/{id}")
def admin_delete_article(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除资讯"""
    article = db.query(NavArticle).filter(NavArticle.id == id).first()
    if not article:
        raise HTTPException(status_code=404, detail="资讯不存在")
    db.delete(article)
    db.commit()
    return {"message": "删除成功"}


# ============ 资讯采集 ============

@router.post("/articles/sync")
def admin_sync_news(
    date: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """手动触发AI资讯采集"""
    from app.tasks.news_sync import sync_daily_news
    result = sync_daily_news(target_date=date, limit=limit)
    return {"message": result}
