# app/routers/front/front_routes.py
from .front_demo import router as front_demo_router
from .nav import router as nav_router
from .front_submit import router as front_submit_router


# 集中引入所有前台路由
front_routers = [
    front_demo_router,
    nav_router,
    front_submit_router,
]
