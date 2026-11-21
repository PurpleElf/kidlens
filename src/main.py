"""FastAPI 入口：API + 静态前端一体服务。

启动：uvicorn src.main:app --host 127.0.0.1 --port 8000
访问：http://localhost:8000/web/          （主页）
      http://localhost:8000/web/review.html （审核台）
      http://localhost:8000/docs            （API 文档）
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.api.gallery_routes import router as gallery_router
from src.api.auth_routes import router as auth_router

ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="KidLens AI", version="0.3.0")
app.include_router(router)
app.include_router(gallery_router)
app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# 静态资源：/web -> web 目录；/data -> data 目录（供前端播放集锦/缩略图）
# 本地单机工具：禁用浏览器缓存，避免改了前端后仍加载旧的 app.js/CSS
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.mount("/web", NoCacheStaticFiles(directory=str(ROOT / "web"), html=True), name="web")
app.mount("/data", StaticFiles(directory=str(ROOT / "data")), name="data")


@app.get("/")
def index():
    return FileResponse(str(ROOT / "web" / "index.html"))
