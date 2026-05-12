# AI Map - AI 工具导航网站

一个展示和推荐 AI 工具的导航网站，支持工具分类、搜索、排行榜、用户提交等功能。

## 功能特性

### 前台功能
- AI 工具分类浏览与搜索
- 工具详情页（含截图、功能介绍、定价信息）
- App Store AI 应用排行榜
- 每日推荐工具
- 用户提交 AI 工具
- AI 截图智能编写

### 后台管理
- 用户管理与 RBAC 权限控制
- 工具分类管理
- 工具提交审核
- 系统配置管理
- 定时任务调度
- 操作日志审计

## 技术栈

| 模块 | 技术 |
|------|------|
| 前台前端 | Nuxt.js 3 + Vue 3 |
| 管理后台 | Vue 3 + Vite |
| 后端 API | Python FastAPI |
| ORM | SQLAlchemy |
| 数据库 | MySQL |
| 任务调度 | APScheduler |

## 项目结构

```
ai-map/
├── admin/                 # 管理后台前端（编译后）
├── mysql/
│   └── dh.sql            # 数据库结构
├── node/
│   ├── public/           # Nuxt 编译后静态文件
│   └── server/           # Node.js 静态服务器
└── serve/
    └── app/
        ├── core/         # 核心模块（配置、数据库、中间件）
        ├── models/       # 数据模型
        ├── routers/      # API 路由
        │   ├── admin_*   # 后台管理路由
        │   └── front/    # 前台路由
        ├── schemas/      # Pydantic 模型
        ├── services/     # 业务服务
        ├── tasks/        # 定时任务
        └── main.py       # FastAPI 入口
```

## 快速部署

### 1. 数据库初始化

```bash
mysql -u root -p < mysql/dh.sql
```

### 2. 后端服务

```bash
cd serve/app
pip install -r requirements.txt
python main.py
```

### 3. 前端服务

```bash
cd node/server
node index.mjs
```

### 4. 反向代理（可选）

推荐使用 Nginx 配置反向代理，统一域名访问前后端服务。

## 环境变量

后端配置文件 `serve/app/.env`:

```env
MYSQL_DSN=mysql+pymysql://user:password@127.0.0.1:3306/dh?charset=utf8mb4
JWT_SECRET=your-secret-key
JWT_ALGO=HS256
ACCESS_EXPIRE_MINUTES=120
CORS_ORIGINS=["http://localhost:3000"]
```

## API 文档

启动后端服务后访问：`http://localhost:8000/docs`

## License

MIT
