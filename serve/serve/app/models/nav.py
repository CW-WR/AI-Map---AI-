# app/models/nav.py
# AI导航工具模型
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, Integer, Text, DateTime, ForeignKey, Boolean
from datetime import datetime
from app.core.db import Base

class NavCategory(Base):
    """工具分类表"""
    __tablename__ = "nav_category"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="分类名称")
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="URL标识")
    icon: Mapped[str | None] = mapped_column(Text, nullable=True, comment="图标（支持emoji、SVG代码、CSS类名）")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="描述")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="状态：1启用 0禁用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    tools: Mapped[list["NavTool"]] = relationship("NavTool", back_populates="category")


class NavTool(Base):
    """AI工具信息表"""
    __tablename__ = "nav_tool"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="工具名称")
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, comment="URL标识")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="简介")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="详细介绍")
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="图标URL")
    cover: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="封面图URL")
    url: Mapped[str] = mapped_column(String(512), nullable=False, comment="官网链接")
    
    # 分类关联
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nav_category.id"), nullable=False)
    category: Mapped["NavCategory"] = relationship("NavCategory", back_populates="tools")
    
    # 价格和功能
    pricing_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="定价类型：免费/付费/ freemium")
    pricing_desc: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="定价说明")
    features: Mapped[str | None] = mapped_column(Text, nullable=True, comment="主要功能，JSON格式")
    
    # 统计数据
    views: Mapped[int] = mapped_column(Integer, default=0, comment="浏览量")
    clicks: Mapped[int] = mapped_column(Integer, default=0, comment="点击量")
    likes: Mapped[int] = mapped_column(Integer, default=0, comment="点赞数")
    hot: Mapped[int] = mapped_column(Integer, default=0, comment="热度值")
    
    # SEO
    seo_title: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="SEO标题")
    seo_desc: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="SEO描述")
    
    # 状态
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否推荐")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="状态：1上架 0下架")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    tags: Mapped[list["NavTag"]] = relationship("NavTag", secondary="nav_tool_tag", back_populates="tools")
    screenshots: Mapped[list["NavToolScreenshot"]] = relationship("NavToolScreenshot", back_populates="tool")


class NavTag(Base):
    """标签表"""
    __tablename__ = "nav_tag"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="标签名称")
    slug: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="URL标识")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="状态")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    tools: Mapped[list["NavTool"]] = relationship("NavTool", secondary="nav_tool_tag", back_populates="tags")


class NavToolTag(Base):
    """工具标签关联表"""
    __tablename__ = "nav_tool_tag"
    
    tool_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nav_tool.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nav_tag.id"), primary_key=True)


class NavToolScreenshot(Base):
    """工具截图表"""
    __tablename__ = "nav_tool_screenshot"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tool_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nav_tool.id"), nullable=False)
    image_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="图片URL")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    tool: Mapped["NavTool"] = relationship("NavTool", back_populates="screenshots")


class NavClickLog(Base):
    """点击记录表（用于推荐算法）"""
    __tablename__ = "nav_click_log"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tool_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nav_tool.id"), nullable=False, comment="工具ID")
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="用户ID")
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="会话ID")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="IP地址")
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="UA")
    source: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="来源页面")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class NavPage(Base):
    """静态页面表（关于我们、用户协议等）"""
    __tablename__ = "nav_page"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="页面标题")
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="URL标识，如 about/terms")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="页面内容（富文本 HTML）")
    meta_desc: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="SEO 描述")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="状态：1启用 0禁用")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AppRanking(Base):
    """App Store AI应用排行榜缓存表"""
    __tablename__ = "nav_app_ranking"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    country: Mapped[str] = mapped_column(String(16), nullable=False, default="cn", comment="国家代码")
    date: Mapped[str] = mapped_column(String(16), nullable=False, comment="排行日期 YYYY-MM-DD")
    rank: Mapped[int] = mapped_column(Integer, nullable=False, comment="排名")
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="App Store应用ID")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="应用名称")
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="图标URL")
    description: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="应用描述")
    rating: Mapped[float | None] = mapped_column(nullable=True, comment="评分")
    rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="评分人数")
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="分类")
    app_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="App Store链接")
    snapshot_date: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="数据快照日期")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class NavMenu(Base):
    """导航菜单表（头部/底部）"""
    __tablename__ = "nav_menu"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False, comment="菜单名称")
    url: Mapped[str] = mapped_column(String(255), nullable=False, comment="跳转链接")
    link_type: Mapped[str] = mapped_column(String(16), default="internal", comment="链接类型：internal内部路由/external外部链接")
    menu_type: Mapped[str] = mapped_column(String(16), default="header", comment="类型：header/footer")
    open_new_tab: Mapped[int] = mapped_column(Integer, default=0, comment="是否新窗口打开（外部链接始终新窗口）")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="状态：1启用 0禁用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class NavFriendlyLink(Base):
    """友情链接表"""
    __tablename__ = "nav_friendly_link"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="站点名称")
    url: Mapped[str] = mapped_column(String(255), nullable=False, comment="链接地址")
    logo: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="站点Logo URL")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="状态：1启用 0禁用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class NavSubmission(Base):
    """工具提交记录表"""
    __tablename__ = "nav_submission"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False, comment="提交的网站URL")
    submitter_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="用户填写的工具名称")
    contact_email: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="联系邮箱（可选）")
    submitter_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="提交者IP")

    # AI/截图处理结果
    ai_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="AI生成工具名")
    ai_slug: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="AI生成slug")
    ai_description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AI生成简介")
    ai_content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AI生成详细介绍")
    ai_pricing_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="AI识别定价类型")
    ai_features: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AI生成功能列表JSON")
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="网站Logo URL")
    screenshots: Mapped[str | None] = mapped_column(Text, nullable=True, comment="截图URL列表JSON")
    ai_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="AI推荐分类ID")
    ai_tag_ids: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="AI推荐标签ID列表，逗号分隔")
    task_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="任务执行日志")

    # 状态：pending/processing/ready/approved/rejected/failed
    status: Mapped[str] = mapped_column(String(32), default="pending", comment="状态")
    task_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="任务失败原因")
    tool_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="审核通过后创建的工具ID")
    admin_note: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="管理员备注")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class NavArticleCategory(Base):
    """资讯分类表"""
    __tablename__ = "nav_article_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="分类名称")
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="URL标识")
    icon: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="图标")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="状态：1启用 0禁用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    articles: Mapped[list["NavArticle"]] = relationship("NavArticle", back_populates="category")


class NavArticle(Base):
    """资讯文章表"""
    __tablename__ = "nav_article"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="标题")
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, comment="URL标识")
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="摘要")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="正文（富文本HTML）")
    cover: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="封面图URL")
    category_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("nav_article_category.id"), nullable=True, comment="分类ID")
    category: Mapped["NavArticleCategory | None"] = relationship("NavArticleCategory", back_populates="articles")
    source: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="来源")
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="原文链接")
    author: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="作者")
    views: Mapped[int] = mapped_column(Integer, default=0, comment="阅读量")
    is_top: Mapped[int] = mapped_column(Integer, default=0, comment="是否置顶：1是 0否")
    status: Mapped[int] = mapped_column(Integer, default=0, comment="状态：1发布 0草稿")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="发布时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
