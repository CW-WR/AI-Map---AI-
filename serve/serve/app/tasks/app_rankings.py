# app/tasks/app_rankings.py
# 每日App Store AI应用排行榜采集任务
# 调用 aihaocanmou 开放平台 app-rankings 接口

import logging
import httpx
from datetime import date

logger = logging.getLogger("app_rankings")

API_BASE = "https://api.aihaocanmou.aizhaozi.com"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def fetch_app_rankings(country: str = "cn", target_date: str = None):
    """
    每日定时任务入口（同步函数）
    获取App Store AI应用排行榜数据，写入 nav_app_ranking 表

    Args:
        country: 国家代码，默认 cn
        target_date: 日期字符串 YYYY-MM-DD，默认为今天
    """
    from app.core.db import SessionLocal
    from app.core.config_loader import get_config
    from app.models.nav import AppRanking

    if not target_date:
        target_date = date.today().strftime("%Y-%m-%d")

    logger.info(f"===== 开始采集App Store AI排行榜 国家: {country} 日期: {target_date} =====")

    api_key = get_config("aihaocanmou_api_key", default="")
    if not api_key:
        msg = "未配置 aihaocanmou_api_key，跳过采集"
        logger.error(msg)
        return msg

    # 调用 API
    api_url = f"{API_BASE}/api/v1/open/app-rankings"
    headers = {"X-API-Key": api_key}
    params = {"country": country, "date": target_date}

    logger.info(f"请求API: {api_url}?country={country}&date={target_date}")

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
    rankings = data.get("rankings") or []
    total = data.get("total", len(rankings))
    logger.info(f"API返回 {total} 条排行数据")

    if not rankings:
        msg = f"日期 {target_date} 国家 {country} 无排行数据"
        logger.info(msg)
        return msg

    # 写入数据库（先删除当天同国家的旧数据，再插入新数据）
    db = SessionLocal()
    imported = 0
    try:
        # 删除当天已有数据
        deleted = db.query(AppRanking).filter(
            AppRanking.country == country,
            AppRanking.date == target_date
        ).delete()
        if deleted:
            logger.info(f"清除旧数据 {deleted} 条")

        for item in rankings:
            record = AppRanking(
                country=country,
                date=target_date,
                rank=item.get("rank", 0),
                app_id=item.get("app_id", ""),
                name=item.get("name", ""),
                icon_url=item.get("icon_url"),
                description=item.get("description"),
                rating=item.get("rating"),
                rating_count=item.get("rating_count"),
                category=item.get("category"),
                app_url=item.get("app_url"),
                snapshot_date=item.get("snapshot_date"),
            )
            db.add(record)
            imported += 1

        db.commit()
    except Exception as e:
        db.rollback()
        msg = f"写入数据库失败: {str(e)}"
        logger.error(msg)
        return msg
    finally:
        db.close()

    summary = f"排行榜采集完成 ({country}/{target_date}): 共 {imported} 条"
    logger.info(summary)
    return summary
