import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db, close_db
from app.api import users, movies, ratings,recommend
from app.api import favorites

app = FastAPI(title="电影推荐系统API")
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# 允许跨域，方便前端调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await init_db()
    print("数据库连接成功！")

@app.on_event("shutdown")
async def shutdown_event():
    await close_db()
    print("数据库连接已关闭。")

# 核心接口
app.include_router(users.router, prefix="/api/auth", tags=["认证"])
app.include_router(movies.router, prefix="/api/movies", tags=["电影"])
app.include_router(ratings.router, prefix="/api/ratings", tags=["评分"])
app.include_router(recommend.router, prefix="/api/recommend", tags=["推荐"])
app.include_router(favorites.router, prefix="/api/favorites", tags=["收藏"])

@app.get("/")
async def root():
    return {"message": "后端启动成功，数据库已连接！"}
