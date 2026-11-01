import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import init_db, close_db
from app.avatar_storage import AVATAR_DIR
from app.api import users, movies, ratings, recommend, comments
from app.api import favorites
from app.api import admin

app = FastAPI(title="电影推荐系统API")
logger = logging.getLogger(__name__)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Pydantic may include raw request bytes in ``exc.errors()`` when a JSON
    # endpoint receives form data. Convert them before JSONResponse serializes.
    detail = jsonable_encoder(
        exc.errors(),
        custom_encoder={bytes: lambda value: value.decode("utf-8", errors="replace")},
    )
    return JSONResponse(
        status_code=422,
        content={"code": 422, "detail": detail},
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    """Log the traceback server-side without exposing implementation details."""
    logger.exception(
        "Unhandled exception while handling %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"code": 500, "detail": "服务器内部错误"},
    )


app.mount("/uploads", StaticFiles(directory=str(AVATAR_DIR.parent)), name="uploads")
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
app.include_router(comments.router, prefix="/api/comments", tags=["评论"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理员注入"])

@app.get("/")
async def root():
    return {"code": 200, "data": {"message": "后端启动成功，数据库已连接！"}}
