# app/services/snapshot_ai_service.py
# 截图 & AI 智能编写服务 - 对接 aihaocanmou 开放平台
import json
import re
import logging
from datetime import datetime
import httpx
from typing import Optional
from app.core.config_loader import get_config

logger = logging.getLogger("submission")

# API Base URL 写死（稳定不变）
API_BASE = "https://api.aihaocanmou.aizhaozi.com"

# 请求超时配置
TIMEOUT = httpx.Timeout(60.0, connect=15.0)


def _get_api_key() -> str:
    """从数据库配置读取 API Key"""
    return get_config("aihaocanmou_api_key", default="")


def _get_headers(with_content_type=False) -> dict:
    headers = {"X-API-Key": _get_api_key()}
    if with_content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _ts() -> str:
    """当前时间戳字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _append_log(submission, msg: str):
    """向 submission.task_log 追加一行日志"""
    line = f"[{_ts()}] {msg}"
    logger.info(f"[submission#{submission.id}] {msg}")
    if submission.task_log:
        submission.task_log += "\n" + line
    else:
        submission.task_log = line


# ============ 截图 API ============

async def fetch_snapshot(url: str) -> dict:
    """
    调用截图API，获取网站截图和Logo
    返回: { logo_url, screenshots: [url, ...] }
    """
    api_url = f"{API_BASE}/api/v1/open/website-snapshot"
    params = {
        "url": url,
        "capture_screenshot": "true",
        "capture_logo": "true",
        "max_screenshots": 4,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(api_url, headers=_get_headers(), params=params)
        if resp.status_code != 200:
            body = resp.text[:500]
            raise Exception(f"截图API返回 {resp.status_code}: {body}")
        data = resp.json()

    # API 返回格式: { code, message, data: { logo_url, screenshots: [...] } }
    inner = data.get("data") or data  # 兼容有无 data 包裹

    logo_url = inner.get("logo_url") or None
    raw_shots = inner.get("screenshots") or []
    screenshots = []
    for s in raw_shots:
        if isinstance(s, str):
            screenshots.append(s)
        elif isinstance(s, dict):
            screenshots.append(s.get("url") or s.get("image_url") or "")
    screenshots = [s for s in screenshots if s]

    return {"logo_url": logo_url, "screenshots": screenshots}


# ============ AI 智能编写 ============

def _build_ai_prompt(url: str, tool_name: str, logo_url: Optional[str],
                     screenshot_urls: Optional[list],
                     category_list: list, tag_list: list) -> str:
    """构建 AI Prompt，包含分类和标签供其选择"""
    screenshot_hint = ""
    if screenshot_urls:
        screenshot_hint = f"\n网站截图（供参考）：{', '.join(screenshot_urls[:2])}"

    name_hint = ""
    if tool_name:
        name_hint = f"\n用户提供的工具名称：{tool_name}"

    # 构建分类列表
    cat_list_str = "\n".join([f"  - ID:{c['id']} 名称:{c['name']}" for c in category_list])
    tag_list_str = "\n".join([f"  - ID:{t['id']} 名称:{t['name']}" for t in tag_list])

    prompt = f"""请根据以下网站信息，用中文生成一个AI工具导航条目的详细介绍，并自动选择最匹配的分类和标签。

网站URL：{url}{name_hint}{screenshot_hint}

=== 可选分类（必须选择1个最匹配的）===
{cat_list_str}

=== 可选标签（选择1-5个最匹配的）===
{tag_list_str}

请严格按照以下 JSON 格式输出，不要包含任何其他文字：
{{
  "name": "工具的英文或品牌名称（简短，2-20字符）",
  "slug": "url-friendly的小写英文标识（只含字母数字和连字符，如 chatgpt）",
  "description": "一句话简介，说明核心功能（中文，30-80字）",
  "content": "详细介绍，包含：产品特点、使用场景、目标用户（中文，150-300字）",
  "pricing_type": "免费/付费/freemium 三选一",
  "features": ["功能点1", "功能点2", "功能点3", "功能点4", "功能点5"],
  "category_id": 最匹配的分类ID（数字）,
  "tag_ids": [匹配的标签ID列表，如 1,2,3]
}}"""
    return prompt


async def ai_write_tool_info(url: str, tool_name: str = "",
                              logo_url: Optional[str] = None,
                              screenshot_urls: Optional[list] = None,
                              category_list: list = None,
                              tag_list: list = None) -> dict:
    """
    调用 AI 大模型，根据网站URL智能生成工具信息+推荐分类标签
    """
    api_url = f"{API_BASE}/api/v1/ai/chat"

    prompt = _build_ai_prompt(url, tool_name, logo_url, screenshot_urls,
                              category_list or [], tag_list or [])

    payload = {
        "model": "deepseek",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1500,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(api_url, headers=_get_headers(with_content_type=True), json=payload)
        if resp.status_code != 200:
            body = resp.text[:500]
            raise Exception(f"AI接口返回 {resp.status_code}: {body}")
        data = resp.json()

    # 提取AI回复内容
    content = ""
    choices = data.get("choices") or []
    if choices:
        content = choices[0].get("message", {}).get("content", "")
    if not content:
        content = data.get("content") or data.get("result") or ""

    result = _parse_ai_json(content)
    return result


def _parse_ai_json(text: str) -> dict:
    """从AI回复中提取JSON，容错处理"""
    text = text.strip()
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

    return {
        "name": "", "slug": "", "description": "", "content": "",
        "pricing_type": "免费", "features": [],
        "category_id": None, "tag_ids": [],
    }


# ============ 完整处理流程 ============

async def process_submission_async(submission_id: int):
    """
    完整处理一条提交记录（严格顺序）：
    Step 1: 截图 → 等待完成 → 记录结果
    Step 2: AI写作（含自动分类标签） → 等待完成 → 记录结果
    Step 3: 自动匹配分类和标签 → 写入数据库
    只有全部完成才标记为 ready
    """
    from app.core.db import SessionLocal
    from app.models.nav import NavSubmission, NavCategory, NavTag

    db = SessionLocal()
    try:
        submission = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
        if not submission:
            logger.error(f"[submission#{submission_id}] 记录不存在，跳过")
            return

        # 初始化日志
        submission.task_log = None
        submission.status = "processing"
        db.commit()

        url = submission.url
        tool_name = submission.submitter_name or ""
        _append_log(submission, f"开始处理提交 #{submission.id}，URL: {url}，名称: {tool_name}")
        db.commit()

        # ===== Step 1: 截图 =====
        _append_log(submission, "── Step 1: 开始截图 ──")
        db.commit()

        logo_url = None
        screenshots = []
        snap_ok = False

        try:
            _append_log(submission, f"调用截图API: {API_BASE}/api/v1/open/website-snapshot")
            db.commit()

            snap = await fetch_snapshot(url)
            logo_url = snap.get("logo_url")
            screenshots = snap.get("screenshots", [])

            _append_log(submission, f"截图完成: logo={'有' if logo_url else '无'}, 截图{len(screenshots)}张")
            if logo_url:
                _append_log(submission, f"  Logo URL: {logo_url}")
            for i, s in enumerate(screenshots):
                _append_log(submission, f"  截图[{i+1}]: {s}")
            snap_ok = True

        except Exception as e:
            _append_log(submission, f"截图失败: {str(e)}")
            _append_log(submission, "截图失败不影响后续流程，继续AI写作")

        # 保存截图结果（不管成功失败都先存）
        submission.logo_url = logo_url
        submission.screenshots = json.dumps(screenshots) if screenshots else None
        db.commit()

        # ===== Step 2: AI 智能写作 =====
        _append_log(submission, "── Step 2: 开始AI智能写作 ──")
        db.commit()

        # 先读取所有分类和标签，传给AI
        categories = db.query(NavCategory).filter(NavCategory.status == 1).order_by(NavCategory.sort).all()
        tags = db.query(NavTag).filter(NavTag.status == 1).order_by(NavTag.sort).all()

        cat_list = [{"id": c.id, "name": c.name} for c in categories]
        tag_list = [{"id": t.id, "name": t.name} for t in tags]
        _append_log(submission, f"已加载 {len(cat_list)} 个分类、{len(tag_list)} 个标签供AI选择")
        db.commit()

        try:
            _append_log(submission, f"调用AI接口: {API_BASE}/api/v1/ai/chat (model=deepseek)")
            db.commit()

            ai_info = await ai_write_tool_info(
                url=url,
                tool_name=tool_name,
                logo_url=logo_url,
                screenshot_urls=screenshots,
                category_list=cat_list,
                tag_list=tag_list,
            )

            _append_log(submission, f"AI写作完成，返回字段: {list(ai_info.keys())}")
            _append_log(submission, f"  AI name: {ai_info.get('name')}")
            _append_log(submission, f"  AI slug: {ai_info.get('slug')}")
            _append_log(submission, f"  AI description: {(ai_info.get('description') or '')[:60]}...")
            _append_log(submission, f"  AI pricing: {ai_info.get('pricing_type')}")
            _append_log(submission, f"  AI features: {ai_info.get('features')}")
            _append_log(submission, f"  AI category_id: {ai_info.get('category_id')}")
            _append_log(submission, f"  AI tag_ids: {ai_info.get('tag_ids')}")

        except Exception as e:
            _append_log(submission, f"AI写作失败: {str(e)}")
            submission.status = "failed"
            submission.task_error = f"AI写作失败：{str(e)}"
            db.commit()
            return

        # ===== Step 3: 保存结果 + 自动匹配分类标签 =====
        _append_log(submission, "── Step 3: 保存结果 ──")

        # 保存AI生成内容
        submission.ai_name = ai_info.get("name") or tool_name or ""
        submission.ai_slug = ai_info.get("slug") or ""
        submission.ai_description = ai_info.get("description") or ""
        submission.ai_content = ai_info.get("content") or ""
        submission.ai_pricing_type = ai_info.get("pricing_type") or "免费"
        features = ai_info.get("features") or []
        submission.ai_features = json.dumps(features, ensure_ascii=False) if features else None

        # 自动匹配分类
        ai_cat_id = ai_info.get("category_id")
        if ai_cat_id:
            # 验证分类确实存在
            valid_cat_ids = {c.id for c in categories}
            if int(ai_cat_id) in valid_cat_ids:
                submission.ai_category_id = int(ai_cat_id)
                cat_name = next((c.name for c in categories if c.id == int(ai_cat_id)), "?")
                _append_log(submission, f"自动分类: {cat_name} (ID:{ai_cat_id})")
            else:
                _append_log(submission, f"AI推荐的分类ID {ai_cat_id} 不存在，跳过自动分类")
        else:
            _append_log(submission, "AI未返回分类推荐")

        # 自动匹配标签
        ai_tag_ids = ai_info.get("tag_ids") or []
        if ai_tag_ids:
            valid_tag_ids = {t.id for t in tags}
            matched = [int(tid) for tid in ai_tag_ids if int(tid) in valid_tag_ids]
            if matched:
                submission.ai_tag_ids = ",".join(str(tid) for tid in matched)
                tag_names = [t.name for t in tags if t.id in matched]
                _append_log(submission, f"自动标签: {', '.join(tag_names)} (IDs:{matched})")
            else:
                _append_log(submission, f"AI推荐的标签IDs {ai_tag_ids} 均不存在")
        else:
            _append_log(submission, "AI未返回标签推荐")

        # 标记完成
        submission.task_error = None
        if not snap_ok:
            submission.task_error = "注意：截图步骤失败，其他步骤正常"
        submission.status = "ready"
        _append_log(submission, f"处理完成，状态变为 ready")
        db.commit()

    except Exception as e:
        logger.exception(f"[submission#{submission_id}] 处理异常")
        try:
            submission = db.query(NavSubmission).filter(NavSubmission.id == submission_id).first()
            if submission:
                _append_log(submission, f"未知异常: {str(e)}")
                submission.status = "failed"
                submission.task_error = str(e)[:2000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
