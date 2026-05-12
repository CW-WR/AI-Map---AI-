# app/routers/front/nav.py
# 前台导航API路由
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from typing import List, Optional
from pydantic import BaseModel

from app.core.db import get_db
from app.models.nav import NavCategory, NavTool, NavTag, NavToolTag, NavClickLog, NavPage, NavMenu, NavFriendlyLink, AppRanking, NavArticle, NavArticleCategory

router = APIRouter(prefix="/api/front/nav", tags=["前台-导航"])


# ============ 响应模型 ============

class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    icon: Optional[str]
    description: Optional[str]
    tool_count: int = 0
    
    class Config:
        from_attributes = True


class TagOut(BaseModel):
    id: int
    name: str
    slug: str
    
    class Config:
        from_attributes = True


class ToolListOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    icon: Optional[str]
    cover: Optional[str]
    url: Optional[str]
    category_name: str
    category_slug: str
    tags: List[str]
    views: int
    hot: int
    pricing_type: Optional[str]
    screenshots: List[str] = []
    
    class Config:
        from_attributes = True


class ToolDetailOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    content: Optional[str]
    icon: Optional[str]
    cover: Optional[str]
    url: str
    category_name: str
    category_slug: str
    tags: List[str]
    views: int
    hot: int
    pricing_type: Optional[str]
    pricing_desc: Optional[str]
    features: List[str]
    screenshots: List[str]
    
    class Config:
        from_attributes = True


class ToolListResponse(BaseModel):
    list: List[ToolListOut]
    total: int
    page: int
    page_size: int


# ============ 分类接口 ============

@router.get("/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db)):
    """获取所有分类"""
    categories = db.query(NavCategory).filter(
        NavCategory.status == 1
    ).order_by(NavCategory.sort.asc()).all()
    
    result = []
    for cat in categories:
        tool_count = db.query(NavTool).filter(
            NavTool.category_id == cat.id,
            NavTool.status == 1
        ).count()
        
        result.append({
            "id": cat.id,
            "name": cat.name,
            "slug": cat.slug,
            "icon": cat.icon,
            "description": cat.description,
            "tool_count": tool_count
        })
    
    return result


@router.get("/categories/{slug}", response_model=CategoryOut)
def get_category(slug: str, db: Session = Depends(get_db)):
    """获取分类详情"""
    category = db.query(NavCategory).filter(
        NavCategory.slug == slug,
        NavCategory.status == 1
    ).first()
    
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    
    tool_count = db.query(NavTool).filter(
        NavTool.category_id == category.id,
        NavTool.status == 1
    ).count()
    
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "icon": category.icon,
        "description": category.description,
        "tool_count": tool_count
    }


# ============ 工具接口 ============

@router.get("/tools", response_model=ToolListResponse)
def get_tools(
    category: Optional[str] = Query(None, description="分类slug"),
    tag: Optional[str] = Query(None, description="标签name"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    sort: str = Query("hot", description="排序：hot/new"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """获取工具列表"""
    query = db.query(NavTool).filter(NavTool.status == 1)
    
    # 分类筛选
    if category:
        cat = db.query(NavCategory).filter(NavCategory.slug == category).first()
        if cat:
            query = query.filter(NavTool.category_id == cat.id)
    
    # 标签筛选（用name查询）
    if tag:
        tag_obj = db.query(NavTag).filter(NavTag.name == tag).first()
        if tag_obj:
            query = query.join(NavToolTag, NavTool.id == NavToolTag.tool_id).filter(NavToolTag.tag_id == tag_obj.id)
    
    # 关键词搜索
    if keyword:
        query = query.filter(
            NavTool.name.contains(keyword) | 
            NavTool.description.contains(keyword)
        )
    
    # 排序
    if sort == "new":
        query = query.order_by(desc(NavTool.created_at))
    else:
        query = query.order_by(desc(NavTool.hot), desc(NavTool.views))
    
    # 分页
    total = query.count()
    tools = query.options(
        joinedload(NavTool.category),
        joinedload(NavTool.tags),
        joinedload(NavTool.screenshots)
    ).offset((page - 1) * page_size).limit(page_size).all()
    
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
            "category_name": tool.category.name if tool.category else "",
            "category_slug": tool.category.slug if tool.category else "",
            "tags": [tag.name for tag in tool.tags],
            "views": tool.views,
            "hot": tool.hot,
            "pricing_type": tool.pricing_type,
            "screenshots": [s.image_url for s in tool.screenshots]
        })
    
    return {
        "list": result,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/tools/{slug}", response_model=ToolDetailOut)
def get_tool_detail(slug: str, db: Session = Depends(get_db)):
    """获取工具详情"""
    tool = db.query(NavTool).options(
        joinedload(NavTool.category),
        joinedload(NavTool.tags),
        joinedload(NavTool.screenshots)
    ).filter(
        NavTool.slug == slug,
        NavTool.status == 1
    ).first()
    
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    
    # 增加浏览量
    tool.views += 1
    db.commit()
    
    # 解析功能列表
    import json
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
        "category_name": tool.category.name if tool.category else "",
        "category_slug": tool.category.slug if tool.category else "",
        "tags": [tag.name for tag in tool.tags],
        "views": tool.views,
        "hot": tool.hot,
        "pricing_type": tool.pricing_type,
        "pricing_desc": tool.pricing_desc,
        "features": features,
        "screenshots": [s.image_url for s in tool.screenshots]
    }


@router.post("/tools/{slug}/click")
def record_click(
    slug: str,
    db: Session = Depends(get_db)
):
    """记录工具点击"""
    tool = db.query(NavTool).filter(NavTool.slug == slug).first()
    if tool:
        tool.clicks += 1
        tool.views += 1
        tool.hot = min(100, tool.hot + 1)  # 热度值增加，上限100
        db.commit()
    
    return {"success": True}


# ============ 推荐接口 ============

@router.get("/recommend/hot", response_model=List[ToolListOut])
def get_hot_tools(
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """获取热门工具"""
    tools = db.query(NavTool).filter(
        NavTool.status == 1
    ).order_by(
        desc(NavTool.hot)
    ).limit(limit).all()
    
    result = []
    for tool in tools:
        result.append({
            "id": tool.id,
            "name": tool.name,
            "slug": tool.slug,
            "description": tool.description,
            "icon": tool.icon,
            "cover": tool.cover,
            "category_name": tool.category.name if tool.category else "",
            "category_slug": tool.category.slug if tool.category else "",
            "tags": [tag.name for tag in tool.tags],
            "views": tool.views,
            "hot": tool.hot,
            "pricing_type": tool.pricing_type
        })
    
    return result


@router.get("/recommend/weekly", response_model=List[ToolListOut])
def get_weekly_popular(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """上周最受欢迎工具（按浏览量降序）"""
    from datetime import datetime, timedelta
    one_week_ago = datetime.now() - timedelta(days=7)
    
    tools = db.query(NavTool).filter(
        NavTool.status == 1
    ).options(
        joinedload(NavTool.category),
        joinedload(NavTool.tags),
        joinedload(NavTool.screenshots)
    ).order_by(
        desc(NavTool.views)
    ).limit(limit).all()
    
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
            "category_name": tool.category.name if tool.category else "",
            "category_slug": tool.category.slug if tool.category else "",
            "tags": [tag.name for tag in tool.tags],
            "views": tool.views,
            "hot": tool.hot,
            "pricing_type": tool.pricing_type,
            "screenshots": [s.image_url for s in tool.screenshots]
        })
    
    return result


@router.get("/recommend/related/{slug}", response_model=List[ToolListOut])
def get_related_tools(
    slug: str,
    limit: int = Query(6, ge=1, le=10),
    db: Session = Depends(get_db)
):
    """获取相关工具（同分类优先，不足则补充同标签的）"""
    tool = db.query(NavTool).options(
        joinedload(NavTool.tags)
    ).filter(NavTool.slug == slug).first()
    if not tool:
        return []
    
    found_ids = {tool.id}
    related = []
    
    # 1. 同分类的工具
    if tool.category_id:
        same_cat = db.query(NavTool).filter(
            NavTool.category_id == tool.category_id,
            NavTool.id != tool.id,
            NavTool.status == 1
        ).options(
            joinedload(NavTool.category),
            joinedload(NavTool.tags),
            joinedload(NavTool.screenshots)
        ).order_by(desc(NavTool.hot)).limit(limit).all()
        for t in same_cat:
            if t.id not in found_ids:
                related.append(t)
                found_ids.add(t.id)
    
    # 2. 不足则补充同标签的
    if len(related) < limit and tool.tags:
        tag_ids = [tag.id for tag in tool.tags]
        if tag_ids:
            same_tag = db.query(NavTool).filter(
                NavTool.id.notin_(found_ids),
                NavTool.status == 1,
                NavTool.tags.any(NavTag.id.in_(tag_ids))
            ).options(
                joinedload(NavTool.category),
                joinedload(NavTool.tags),
                joinedload(NavTool.screenshots)
            ).order_by(desc(NavTool.hot)).limit(limit - len(related)).all()
            for t in same_tag:
                if t.id not in found_ids:
                    related.append(t)
                    found_ids.add(t.id)
    
    # 3. 还不足则补充热门工具
    if len(related) < limit:
        hot_tools = db.query(NavTool).filter(
            NavTool.id.notin_(found_ids),
            NavTool.status == 1
        ).options(
            joinedload(NavTool.category),
            joinedload(NavTool.tags),
            joinedload(NavTool.screenshots)
        ).order_by(desc(NavTool.hot)).limit(limit - len(related)).all()
        for t in hot_tools:
            if t.id not in found_ids:
                related.append(t)
                found_ids.add(t.id)
    
    result = []
    for t in related[:limit]:
        result.append({
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "description": t.description,
            "icon": t.icon,
            "cover": t.cover,
            "url": t.url,
            "category_name": t.category.name if t.category else "",
            "category_slug": t.category.slug if t.category else "",
            "tags": [tag.name for tag in t.tags],
            "views": t.views,
            "hot": t.hot,
            "pricing_type": t.pricing_type,
            "screenshots": [s.image_url for s in t.screenshots]
        })
    
    return result


# ============ AI 智能推荐 ============

class AiChatRequest(BaseModel):
    message: str
    history: list = []  # [{"role": "user"/"assistant", "content": "..."}]


@router.post("/recommend/ai-chat")
def ai_recommend_chat(
    req: AiChatRequest,
    db: Session = Depends(get_db)
):
    """
    AI智能推荐对话：用户描述需求，AI分析后推荐最合适的工具
    """
    import httpx
    import json
    import re
    from app.core.config_loader import get_config

    api_key = get_config("aihaocanmou_api_key", default="")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI服务未配置")

    # 获取所有上架工具的摘要信息，供AI参考
    tools = db.query(NavTool).options(
        joinedload(NavTool.category),
        joinedload(NavTool.tags)
    ).filter(NavTool.status == 1).order_by(desc(NavTool.hot)).limit(200).all()

    tool_list_text = ""
    for t in tools:
        cat = t.category.name if t.category else ""
        tags = ",".join([tg.name for tg in t.tags][:5])
        pricing = t.pricing_type or ""
        tool_list_text += f"- {t.name}(slug:{t.slug}) | 分类:{cat} | 标签:{tags} | 定价:{pricing} | 简介:{(t.description or '')[:80]}\n"

    system_prompt = f"""你是一个AI工具导航网站的智能推荐助手。
你的任务是根据用户的需求，从以下工具库中推荐最合适的工具。

## 工具库
{tool_list_text}

## 回复规则
1. 分析用户需求，推荐 2-5 个最合适的工具
2. 对每个推荐的工具，用1-2句话说明推荐理由
3. 回复末尾必须附加一个JSON块，格式如下（用```json```包裹）：
```json
{{"recommended_slugs": ["slug1", "slug2", "slug3"]}}
```
4. 回复使用中文，语气友好专业
5. 如果用户的需求与AI工具无关，也要友好回复并尝试引导"""

    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]
    # 添加历史对话（最近6轮）
    for h in (req.history or [])[-12:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    # 调用AI
    payload = {
        "model": "deepseek",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    api_base = "https://api.aihaocanmou.aizhaozi.com"

    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
            resp = client.post(f"{api_base}/api/v1/ai/chat", headers=headers, json=payload)
            if resp.status_code != 200:
                raise Exception(f"AI接口返回 {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
    except Exception as e:
        # AI调用失败，降级到关键词搜索
        fallback_tools = db.query(NavTool).options(
            joinedload(NavTool.category), joinedload(NavTool.tags)
        ).filter(
            NavTool.status == 1,
            NavTool.name.contains(req.message) | NavTool.description.contains(req.message)
        ).order_by(desc(NavTool.hot)).limit(4).all()

        return {
            "reply": f"抱歉，AI服务暂时不可用，我先用关键词为你搜索相关工具：",
            "tools": [_format_tool(t) for t in fallback_tools]
        }

    # 提取AI回复
    ai_text = ""
    choices = data.get("choices") or []
    if choices:
        ai_text = choices[0].get("message", {}).get("content", "")
    if not ai_text:
        ai_text = data.get("content") or data.get("result") or "抱歉，AI未返回有效回复。"

    # 从AI回复中提取推荐的slug列表
    recommended_slugs = []
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", ai_text, re.DOTALL)
    if json_match:
        try:
            json_data = json.loads(json_match.group(1))
            recommended_slugs = json_data.get("recommended_slugs", [])
        except Exception:
            pass

    if not recommended_slugs:
        # 尝试直接匹配JSON
        json_match2 = re.search(r'\{[^{}]*"recommended_slugs"\s*:\s*\[.*?\][^{}]*\}', ai_text, re.DOTALL)
        if json_match2:
            try:
                json_data = json.loads(json_match2.group(0))
                recommended_slugs = json_data.get("recommended_slugs", [])
            except Exception:
                pass

    # 清理AI回复文本（移除JSON块）
    clean_reply = re.sub(r"```json\s*\{.*?\}\s*```", "", ai_text, flags=re.DOTALL).strip()
    clean_reply = re.sub(r'\{[^{}]*"recommended_slugs"\s*:\s*\[.*?\][^{}]*\}', "", clean_reply, flags=re.DOTALL).strip()

    # 查询推荐的工具详情
    recommended_tools = []
    if recommended_slugs:
        tool_objs = db.query(NavTool).options(
            joinedload(NavTool.category),
            joinedload(NavTool.tags),
            joinedload(NavTool.screenshots)
        ).filter(
            NavTool.slug.in_(recommended_slugs),
            NavTool.status == 1
        ).all()
        # 按推荐顺序排列
        tool_map = {t.slug: t for t in tool_objs}
        for slug in recommended_slugs:
            if slug in tool_map:
                recommended_tools.append(tool_map[slug])

    return {
        "reply": clean_reply,
        "tools": [_format_tool(t) for t in recommended_tools]
    }


def _format_tool(t):
    """格式化工具输出"""
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "description": t.description,
        "icon": t.icon,
        "cover": t.cover,
        "url": t.url,
        "category_name": t.category.name if t.category else "",
        "category_slug": t.category.slug if t.category else "",
        "tags": [tag.name for tag in t.tags],
        "views": t.views,
        "hot": t.hot,
        "pricing_type": t.pricing_type,
        "screenshots": [s.image_url for s in t.screenshots] if hasattr(t, 'screenshots') and t.screenshots else []
    }


# ============ 标签接口 ============

class TagWithCountOut(BaseModel):
    id: int
    name: str
    slug: str
    tool_count: int = 0
    
    class Config:
        from_attributes = True


@router.get("/tags", response_model=List[TagWithCountOut])
def get_tags(db: Session = Depends(get_db)):
    """获取所有标签（带工具数量）"""
    tags = db.query(NavTag).filter(
        NavTag.status == 1
    ).order_by(NavTag.sort.asc()).all()
    
    result = []
    for tag in tags:
        tool_count = db.query(NavTool).filter(
            NavTool.tags.any(id=tag.id),
            NavTool.status == 1
        ).count()
        result.append({
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "tool_count": tool_count
        })
    
    return result


@router.get("/tags/{slug}")
def get_tag_detail(
    slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """获取标签详情及工具列表（用name查询）"""
    tag = db.query(NavTag).filter(
        NavTag.name == slug
    ).first()
    
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    
    # 查询该标签的工具 - 显式 JOIN 中间表
    query = db.query(NavTool).options(
        joinedload(NavTool.category),
        joinedload(NavTool.tags)
    ).join(NavToolTag, NavTool.id == NavToolTag.tool_id).filter(
        NavToolTag.tag_id == tag.id,
        NavTool.status == 1
    )
    
    total = query.count()
    tools = query.order_by(desc(NavTool.hot)).offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for tool in tools:
        result.append({
            "id": tool.id,
            "name": tool.name,
            "slug": tool.slug,
            "description": tool.description,
            "icon": tool.icon,
            "cover": tool.cover,
            "category_name": tool.category.name if tool.category else "",
            "category_slug": tool.category.slug if tool.category else "",
            "tags": [t.name for t in tool.tags],
            "views": tool.views,
            "hot": tool.hot,
            "pricing_type": tool.pricing_type
        })
    
    return {
        "tag": {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug
        },
        "tools": {
            "list": result,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    }


@router.get("/pages/{slug}")
def get_page_by_slug(
    slug: str,
    db: Session = Depends(get_db)
):
    """前台获取静态页面内容（按 slug）"""
    page = db.query(NavPage).filter(
        NavPage.slug == slug,
        NavPage.status == 1
    ).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    return {
        "id": page.id,
        "title": page.title,
        "slug": page.slug,
        "content": page.content,
        "meta_desc": page.meta_desc,
        "updated_at": page.updated_at.strftime("%Y-%m-%d") if page.updated_at else ""
    }


@router.get("/menus")
def get_menus(menu_type: str = "header", db: Session = Depends(get_db)):
    """前台获取菜单列表"""
    menus = db.query(NavMenu).filter(
        NavMenu.menu_type == menu_type,
        NavMenu.status == 1
    ).order_by(NavMenu.sort, NavMenu.id).all()
    return [{"id": m.id, "title": m.title, "url": m.url, "open_new_tab": m.open_new_tab} for m in menus]


@router.get("/links")
def get_links(db: Session = Depends(get_db)):
    """前台获取友情链接"""
    links = db.query(NavFriendlyLink).filter(
        NavFriendlyLink.status == 1
    ).order_by(NavFriendlyLink.sort, NavFriendlyLink.id).all()
    return [{"id": l.id, "name": l.name, "url": l.url, "logo": l.logo} for l in links]


@router.post("/tools/by-slugs", response_model=List[ToolListOut])
def get_tools_by_slugs(
    slugs: List[str],
    db: Session = Depends(get_db)
):
    """批量按slug获取工具（用于收藏列表）"""
    if not slugs or len(slugs) > 100:
        return []
    tools = db.query(NavTool).filter(
        NavTool.status == 1,
        NavTool.slug.in_(slugs)
    ).options(
        joinedload(NavTool.category),
        joinedload(NavTool.tags),
        joinedload(NavTool.screenshots)
    ).all()
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
            "category_name": tool.category.name if tool.category else "",
            "category_slug": tool.category.slug if tool.category else "",
            "tags": [tag.name for tag in tool.tags],
            "views": tool.views,
            "hot": tool.hot,
            "pricing_type": tool.pricing_type,
            "screenshots": [s.image_url for s in tool.screenshots]
        })
    return result


# ============ App Store 排行榜 ============

@router.get("/app-rankings")
def get_app_rankings(
    country: str = Query("cn", description="国家代码"),
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认最新"),
    db: Session = Depends(get_db)
):
    """获取App Store AI应用排行榜"""
    query = db.query(AppRanking).filter(AppRanking.country == country)

    if date:
        query = query.filter(AppRanking.date == date)
    else:
        # 获取最新日期
        latest = db.query(func.max(AppRanking.date)).filter(
            AppRanking.country == country
        ).scalar()
        if not latest:
            return {"country": country, "date": None, "total": 0, "rankings": []}
        query = query.filter(AppRanking.date == latest)
        date = latest

    rankings = query.order_by(AppRanking.rank).all()

    return {
        "country": country,
        "date": date,
        "total": len(rankings),
        "rankings": [
            {
                "rank": r.rank,
                "app_id": r.app_id,
                "name": r.name,
                "icon_url": r.icon_url,
                "description": r.description,
                "rating": r.rating,
                "rating_count": r.rating_count,
                "category": r.category,
                "app_url": r.app_url,
                "snapshot_date": r.snapshot_date,
            }
            for r in rankings
        ]
    }


@router.get("/app-rankings/dates")
def get_app_ranking_dates(
    country: str = Query("cn", description="国家代码"),
    limit: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db)
):
    """获取有排行数据的日期列表"""
    dates = db.query(AppRanking.date).filter(
        AppRanking.country == country
    ).distinct().order_by(desc(AppRanking.date)).limit(limit).all()
    return [d[0] for d in dates]


# ============ 资讯接口 ============

@router.get("/article-categories")
def get_article_categories(db: Session = Depends(get_db)):
    """获取资讯分类列表（前台）"""
    cats = db.query(NavArticleCategory).filter(
        NavArticleCategory.status == 1
    ).order_by(NavArticleCategory.sort).all()
    return [{"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon} for c in cats]


@router.get("/articles")
def get_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    category: Optional[str] = Query(None, description="分类slug"),
    db: Session = Depends(get_db)
):
    """获取资讯列表（前台）"""
    query = db.query(NavArticle).options(
        joinedload(NavArticle.category)
    ).filter(NavArticle.status == 1)

    if category:
        cat = db.query(NavArticleCategory).filter(NavArticleCategory.slug == category).first()
        if cat:
            query = query.filter(NavArticle.category_id == cat.id)

    total = query.count()
    articles = query.order_by(
        desc(NavArticle.is_top),
        desc(NavArticle.published_at),
        desc(NavArticle.created_at)
    ).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "list": [{
            "id": a.id,
            "title": a.title,
            "slug": a.slug,
            "summary": a.summary,
            "cover": a.cover,
            "source": a.source,
            "author": a.author,
            "views": a.views,
            "is_top": a.is_top,
            "category_name": a.category.name if a.category else None,
            "category_slug": a.category.slug if a.category else None,
            "published_at": a.published_at.strftime("%Y-%m-%d") if a.published_at else a.created_at.strftime("%Y-%m-%d")
        } for a in articles],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/articles/{slug}")
def get_article_detail(
    slug: str,
    db: Session = Depends(get_db)
):
    """获取资讯详情（前台）"""
    article = db.query(NavArticle).filter(
        NavArticle.slug == slug,
        NavArticle.status == 1
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="资讯不存在")

    # 增加阅读量
    article.views += 1
    db.commit()

    return {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "summary": article.summary,
        "content": article.content,
        "cover": article.cover,
        "source": article.source,
        "source_url": article.source_url,
        "author": article.author,
        "views": article.views,
        "published_at": article.published_at.strftime("%Y-%m-%d") if article.published_at else article.created_at.strftime("%Y-%m-%d")
    }
