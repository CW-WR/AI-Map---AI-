# app/tasks/daily_tools.py
# 每日AI工具自动采集任务
# 调用 aihaocanmou 开放平台 daily-tools 接口，采集工具到审核列表

import json
import logging
import httpx
from datetime import datetime, date

logger = logging.getLogger("daily_tools")

API_BASE = "https://api.aihaocanmou.aizhaozi.com"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
AI_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


def fetch_daily_tools(target_date: str = None):
    """
    每日定时任务入口（同步函数）
    获取指定日期上线的AI工具，写入 nav_submission 审核列表
    
    Args:
        target_date: 日期字符串 YYYY-MM-DD，默认为今天
    """
    from app.core.db import SessionLocal
    from app.core.config_loader import get_config

    if not target_date:
        target_date = date.today().strftime("%Y-%m-%d")

    logger.info(f"===== 开始执行每日AI工具采集 日期: {target_date} =====")

    api_key = get_config("aihaocanmou_api_key", default="")
    if not api_key:
        msg = "未配置 aihaocanmou_api_key，跳过采集"
        logger.error(msg)
        return msg

    # Step 1: 调用 API
    api_url = f"{API_BASE}/api/v1/open/daily-tools"
    headers = {"X-API-Key": api_key}
    params = {"date": target_date}

    logger.info(f"请求API: {api_url}?date={target_date}")

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
    inner = resp_data.get("data") or resp_data
    tools = inner.get("tools") or []
    total_api = inner.get("total", len(tools))
    logger.info(f"API返回 {total_api} 个工具")

    if not tools:
        msg = f"日期 {target_date} 无新工具"
        logger.info(msg)
        return msg

    # Step 2: 逐个写入审核列表
    db = SessionLocal()
    imported = 0
    skipped = 0
    failed = 0
    details = []

    try:
        from app.models.nav import NavSubmission, NavTool, NavCategory, NavTag

        # 预加载分类和标签用于匹配
        categories = db.query(NavCategory).filter(NavCategory.status == 1).all()
        tags = db.query(NavTag).filter(NavTag.status == 1).all()
        cat_map = {c.name: c.id for c in categories}       # 精确匹配
        cat_list = [(c.name, c.id) for c in categories]     # 用于模糊匹配
        tag_map = {t.name: t.id for t in tags}

        def _match_category(api_cat_name: str) -> tuple:
            """智能匹配分类：精确 > 包含 > 自动创建
            返回 (category_id, match_info_str)
            """
            if not api_cat_name:
                return None, "无分类信息"
            # 1. 精确匹配
            if api_cat_name in cat_map:
                return cat_map[api_cat_name], f"精确匹配 '{api_cat_name}'"
            # 2. 模糊匹配：API返回"AI写作"，本地有"写作"，或本地有"AI写作助手"
            api_lower = api_cat_name.lower().replace(" ", "")
            for local_name, local_id in cat_list:
                local_lower = local_name.lower().replace(" ", "")
                # 互相包含
                if api_lower in local_lower or local_lower in api_lower:
                    cat_map[api_cat_name] = local_id  # 缓存
                    return local_id, f"模糊匹配 '{api_cat_name}' -> '{local_name}'"
            # 3. 无匹配，自动创建
            new_slug = api_cat_name.lower().replace(" ", "-")
            # 检查slug是否已存在
            existing = db.query(NavCategory).filter(NavCategory.slug == new_slug).first()
            if existing:
                cat_map[api_cat_name] = existing.id
                return existing.id, f"slug匹配 '{api_cat_name}' -> '{existing.name}'"
            new_cat = NavCategory(
                name=api_cat_name,
                slug=new_slug,
                sort=0,
                status=1,
            )
            db.add(new_cat)
            db.flush()  # 获取ID
            cat_map[api_cat_name] = new_cat.id
            cat_list.append((api_cat_name, new_cat.id))
            return new_cat.id, f"自动创建分类 '{api_cat_name}' (ID:{new_cat.id})"

        def _match_or_create_tag(tag_name: str) -> tuple:
            """匹配或创建标签，返回 (tag_id, is_new)"""
            if not tag_name:
                return None, False
            # 精确匹配
            if tag_name in tag_map:
                return tag_map[tag_name], False
            # 模糊匹配：互相包含
            tag_lower = tag_name.lower().replace(" ", "")
            for local_name, local_id in tag_map.items():
                local_lower = local_name.lower().replace(" ", "")
                if tag_lower in local_lower or local_lower in tag_lower:
                    tag_map[tag_name] = local_id  # 缓存
                    return local_id, False
            # 自动创建
            new_slug = tag_name.lower().replace(" ", "-")
            existing = db.query(NavTag).filter(NavTag.slug == new_slug).first()
            if existing:
                tag_map[tag_name] = existing.id
                return existing.id, False
            new_tag = NavTag(
                name=tag_name,
                slug=new_slug,
                sort=0,
                status=1,
            )
            db.add(new_tag)
            db.flush()
            tag_map[tag_name] = new_tag.id
            return new_tag.id, True

        for tool in tools:
            name = (tool.get("name") or "").strip()
            slug = (tool.get("slug") or "").strip()
            official_url = (tool.get("official_url") or "").strip()
            logo_url = tool.get("logo_url")
            short_desc = tool.get("short_description") or ""
            full_desc = tool.get("full_description") or ""
            category_name = (tool.get("category") or "").strip()
            pricing_model = (tool.get("pricing_model") or "免费").strip()
            api_tags = tool.get("tags") or []

            # 处理截图
            screenshot_urls = []
            api_screenshots = tool.get("screenshots") or []
            for s in api_screenshots:
                s_url = (s.get("url") or "").strip()
                if s_url:
                    screenshot_urls.append(s_url)
            # 兼容单截图字段
            if not screenshot_urls:
                single_shot = (tool.get("screenshot_url") or "").strip()
                if single_shot:
                    screenshot_urls.append(single_shot)
            # 封面图：优先第一张截图，其次 logo
            cover_url = screenshot_urls[0] if screenshot_urls else logo_url

            if not name or not official_url:
                skipped += 1
                details.append(f"跳过: {name or '无名'} (缺少必要字段)")
                continue

            # 查重：nav_tool 中已存在的跳过
            existing_tool = db.query(NavTool).filter(
                (NavTool.slug == slug) | (NavTool.url == official_url)
            ).first()
            if existing_tool:
                skipped += 1
                details.append(f"跳过: {name} (工具已存在 ID:{existing_tool.id})")
                continue

            # 查重：nav_submission 中已有相同 URL 的跳过
            existing_sub = db.query(NavSubmission).filter(
                NavSubmission.url == official_url
            ).first()
            if existing_sub:
                skipped += 1
                details.append(f"跳过: {name} (提交记录已存在 ID:{existing_sub.id})")
                continue

            try:
                # 智能匹配分类
                ai_category_id, cat_info = _match_category(category_name)

                # 智能匹配/创建标签
                matched_tag_ids = []
                tag_infos = []
                for t in api_tags:
                    t_name = (t.get("name") or "").strip()
                    if not t_name:
                        continue
                    tid, is_new = _match_or_create_tag(t_name)
                    if tid:
                        matched_tag_ids.append(tid)
                        tag_infos.append(f"{t_name}({'new' if is_new else 'match'}:{tid})")

                # 构建任务日志
                log_lines = [
                    f"[{_ts()}] 来源: 每日AI工具采集 ({target_date})",
                    f"[{_ts()}] 原始平台工具ID: {tool.get('id')}",
                    f"[{_ts()}] Logo: {logo_url or '无'}",
                    f"[{_ts()}] 截图: {len(screenshot_urls)} 张",
                    f"[{_ts()}] 封面图: {cover_url or '无'}",
                    f"[{_ts()}] 分类: {cat_info}",
                    f"[{_ts()}] 标签: {', '.join(tag_infos) if tag_infos else '无匹配'}",
                ]

                # 调用AI大模型补全功能特性
                features = []
                try:
                    log_lines.append(f"[{_ts()}] ── 开始AI补全功能特性 ──")
                    ai_result = _ai_enhance_features(
                        name=name,
                        url=official_url,
                        description=short_desc,
                        api_key=api_key,
                    )
                    if ai_result.get("features"):
                        features = ai_result["features"]
                        log_lines.append(f"[{_ts()}] AI补全功能特性: {features}")
                except Exception as e:
                    log_lines.append(f"[{_ts()}] AI补全失败(不影响入库): {str(e)[:100]}")
                    logger.warning(f"AI补全失败 {name}: {str(e)}")

                # 创建提交记录
                submission = NavSubmission(
                    url=official_url,
                    submitter_name=name,
                    contact_email=None,
                    submitter_ip="system:daily-tools",
                    ai_name=name,
                    ai_slug=slug,
                    ai_description=short_desc,
                    ai_content=full_desc,
                    ai_pricing_type=pricing_model,
                    ai_features=json.dumps(features, ensure_ascii=False) if features else None,
                    logo_url=cover_url or logo_url,
                    screenshots=json.dumps(screenshot_urls, ensure_ascii=False) if screenshot_urls else None,
                    ai_category_id=ai_category_id,
                    ai_tag_ids=",".join(str(tid) for tid in matched_tag_ids) if matched_tag_ids else None,
                    task_log="\n".join(log_lines),
                    status="ready",
                    task_error=None,
                )
                db.add(submission)
                db.commit()
                imported += 1
                details.append(f"导入: {name} (submission ID:{submission.id})")

            except Exception as e:
                db.rollback()
                failed += 1
                details.append(f"失败: {name} ({str(e)[:80]})")
                logger.error(f"导入失败: {name} - {str(e)}")

    finally:
        db.close()

    summary = (
        f"每日采集完成 ({target_date}): "
        f"API返回 {total_api} 个, "
        f"导入审核列表 {imported}, 跳过 {skipped}, 失败 {failed}"
    )
    logger.info(summary)
    return summary + "\n" + "\n".join(details)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ai_enhance_features(name: str, url: str, description: str, api_key: str) -> dict:
    """
    调用AI大模型补全工具功能特性
    同步调用，返回 { features: [...], description: "", content: "" }
    """
    import re

    prompt = f"""请根据以下 AI 工具信息，提炼 5 个核心功能特性。

工具名称：{name}
官网地址：{url}
简介：{description[:200]}

请严格按以下 JSON 格式输出，不要包含任何其他文字：
{{
  "features": ["功能点1", "功能点2", "功能点3", "功能点4", "功能点5"]
}}"""

    payload = {
        "model": "deepseek",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=AI_TIMEOUT) as client:
        resp = client.post(f"{API_BASE}/api/v1/ai/chat", headers=headers, json=payload)
        if resp.status_code != 200:
            raise Exception(f"AI接口返回 {resp.status_code}: {resp.text[:200]}")
        data = resp.json()

    # 提取AI回复
    ai_text = ""
    choices = data.get("choices") or []
    if choices:
        ai_text = choices[0].get("message", {}).get("content", "")
    if not ai_text:
        ai_text = data.get("content") or data.get("result") or ""

    # 解析JSON
    text = ai_text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {"features": [], "description": "", "content": ""}

