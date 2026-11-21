#!/bin/bash
# KidLens AI · 班级相册 —— macOS 双击启动脚本
# 用法：在 Finder 里双击本文件；关闭弹出的终端窗口即停止服务。

cd "$(dirname "$0")" || exit 1

PY=".venv/bin/python"
PORT="${KIDLENS_PORT:-8000}"
# 用 127.0.0.1 而不是 localhost：本机 localhost 优先解析到 IPv6，
# 可能命中旧的 IPv6 服务而看到 404。改端口可设环境变量 KIDLENS_PORT。
URL="http://127.0.0.1:${PORT}"

echo "==================================================="
echo "  KidLens AI · 班级相册（单机版）"
echo "==================================================="
echo

# --- 1. 准备 Python 虚拟环境 ---
if [ ! -x "$PY" ]; then
  echo "[1/3] 首次运行，正在创建虚拟环境并安装依赖（可能需要几分钟）..."
  python3 -m venv .venv || { echo "创建虚拟环境失败，请先安装 Python 3。按回车退出。"; read; exit 1; }
  PY=".venv/bin/python"
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1
  "$PY" -m pip install -r requirements.txt || { echo "依赖安装失败。按回车退出。"; read; exit 1; }
  echo "      依赖安装完成。"
else
  echo "[1/3] 虚拟环境已就绪。"
fi

# --- 2. 检查关键依赖 uvicorn，缺失则补装 ---
if ! "$PY" -c "import uvicorn" >/dev/null 2>&1; then
  echo "      检测到缺少依赖，正在补装..."
  "$PY" -m pip install -r requirements.txt || { echo "依赖安装失败。按回车退出。"; read; exit 1; }
fi

# --- 3. 端口已被占用时的处理 ---
# 只有 /health 且 /api/auth/me 都在，才是"当前版本的 KidLens 在跑"。
# 只认 /health 会误把旧版本进程当成新服务（旧版没有登录接口 → 登录报 404）。
if curl -s "${URL}/health" | grep -q 'ok'; then
  if curl -s -o /dev/null -w '%{http_code}' "${URL}/api/auth/me" | grep -q '200'; then
    echo "[!] KidLens 已在运行且是最新版本，直接为你打开登录页。"
    open "${URL}/web/login.html"
    echo "    （如需重启，请先关掉之前那个终端窗口）"
    exit 0
  else
    echo "[!] 检测到 8000 端口上运行的是旧版本 KidLens（没有登录接口），正在为你重启..."
    OLD_PID=$(lsof -ti tcp:${PORT} 2>/dev/null)
    if [ -n "$OLD_PID" ]; then kill $OLD_PID 2>/dev/null; sleep 1; fi
  fi
fi

echo "[2/3] 启动服务：${URL}"
echo "[3/3] 即将自动打开浏览器..."
echo
echo "  登录页：${URL}/web/login.html"
echo "  相册页：${URL}/web/gallery.html"
echo "  停止服务：关闭本终端窗口，或按 Ctrl+C"
echo "  提示：地址请用 127.0.0.1，不要用 localhost（本机 localhost 优先走 IPv6 会命中旧服务）"
echo

# 后台等待服务就绪后打开浏览器（最多等 60 秒）
(
  for i in $(seq 1 60); do
    if curl -s "${URL}/health" | grep -q 'ok'; then
      open "${URL}/web/login.html"
      exit 0
    fi
    sleep 1
  done
) &

# 前台运行服务（关闭终端窗口即停止）
"$PY" -m uvicorn src.main:app --host 127.0.0.1 --port "${PORT}"

echo
echo "KidLens 已停止。"
