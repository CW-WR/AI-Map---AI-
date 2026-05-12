# app/tasks/news_sync.py
# 每日AI资讯自动采集任务
# 调用 aihaocanmou 开放平台 daily-news 接口

import logging
import httpx
from datetime import date, datetime

logger = logging.getLogger("news_sync")

API_BASE = "https://api.aihaocanmou.aizhaozi.com"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# API分类slug -> 本地分类slug 映射
CATEGORY_SLUG_MAP = {
    "industry-news": "industry",
    "tech-progress": "tech",
    "business": "business",
    "policy": "policy",
    "tutorial": "tutorial",
    "opensource": "opensource",
}


def sync_daily_news(target_date: str = None, limit: int = 20):
    """
    每日定时任务入口（同步函数）
    从 aihaocanmou 开放平台获取 AI 资讯，写入 nav_article 表

    Args:
        target_date: 日期字符串 YYYY-MM-DD，默认为今天
        limit: 每次获取条数，默认20
    """
    from app.core.db import SessionLocal
    from app.core.config_loader import get_config
    from app.models.nav import NavArticle, NavArticleCategory

    if not target_date:
        target_date = date.today().strftime("%Y-%m-%d")

    logger.info(f"===== 开始采集AI资讯 日期: {target_date} =====")

    api_key = get_config("aihaocanmou_api_key", default="")
    if not api_key:
        msg = "未配置 aihaocanmou_api_key，跳过采集"
        logger.error(msg)
        return msg

    # 调用 API
    api_url = f"{API_BASE}/api/v1/open/daily-news"
    headers = {"X-API-Key": api_key}
    params = {"date": target_date, "limit": limit}

    logger.info(f"请求API: {api_url}?date={target_date}&limit={limit}")

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(api_url, headers=headers, params=params)
    except Exception as e:
        msg = f"请求API失败: {str(e)}"
        logger.error(msg)
        return msg

    if resp.status_code != 200:
        msg = f"API返回 {resp.status_code}: {resp.text[:500]}"
        logger.error(msg)
        return msg

    resp_data = resp.json()
    if resp_data.get("code") != 200:
        msg = f"API业务错误: {resp_data.get('message', '未知错误')}"
        logger.error(msg)
        return msg

    data = resp_data.get("data") or {}
    news_list = data.get("news") or []
    total = data.get("total", len(news_list))
    logger.info(f"API返回 {total} 条资讯")

    if not news_list:
        msg = f"日期 {target_date} 无资讯数据"
        logger.info(msg)
        return msg

    # 写入数据库
    db = SessionLocal()
    imported = 0
    skipped = 0

    try:
        # 预加载本地分类映射 slug -> id
        local_categories = db.query(NavArticleCategory).all()
        cat_slug_to_id = {c.slug: c.id for c in local_categories}

        for item in news_list:
            slug = item.get("slug", "")
            if not slug:
                skipped += 1
                continue

            # 检查是否已存在（按slug去重）
            existing = db.query(NavArticle).filter(NavArticle.slug == slug).first()
            if existing:
                logger.debug(f"跳过已存在: {slug}")
                skipped += 1
                continue

            # 匹配分类
            category_id = None
            api_category = item.get("category") or {}
            api_cat_slug = api_category.get("slug", "")
            if api_cat_slug:
                local_slug = CATEGORY_SLUG_MAP.get(api_cat_slug, api_cat_slug)
                category_id = cat_slug_to_id.get(local_slug)

            # 解析发布时间
            published_at = None
            pub_str = item.get("published_at")
            if pub_str:
                try:
                    published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except Exception:
                    published_at = datetime.now()

            article = NavArticle(
                title=item.get("title", "")[:200],
                slug=slug[:200],
                summary=item.get("summary", "")[:500] if item.get("summary") else None,
                content=item.get("content"),
                cover=item.get("cover_image"),
                category_id=category_id,
                source=item.get("source", "")[:128] if item.get("source") else None,
                source_url=item.get("source_url", "")[:512] if item.get("source_url") else None,
                author=item.get("author", "")[:64] if item.get("author") else None,
                views=item.get("view_count", 0),
                is_top=1 if item.get("is_top") else 0,
                status=1,  # 直接发布
                sort=0,
                published_at=published_at,
            )
            db.add(article)
            imported += 1

        db.commit()
    except Exception as e:
        db.rollback()
        msg = f"写入数据库失败: {str(e)}"
        logger.error(msg)
        return msg
    finally:
        db.close()

    summary = f"资讯采集完成 ({target_date}): 新增 {imported} 条, 跳过 {skipped} 条"
    logger.info(summary)
    return summary
