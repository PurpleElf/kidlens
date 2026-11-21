# KidLens AI · 班级相册（单机版）

把班级活动的照片、视频按孩子自动分拣归档，做成可按日期翻看的私人相册。

定位：**单机实际使用**（不上线、量少），同时保留演示看点与成长手账。目标机器 Mac M5 / 16GB / 512GB。
全流程本地处理，数据不出设备；无需 Docker / MinIO。

## 角色与登录（教师版 / 家长版）

双击启动脚本、浏览器打开后先到**登录页**（`http://127.0.0.1:8000/web/login.html`）。本机演示账号：

| 身份 | 账号 | 密码 | 能做什么 |
|---|---|---|---|
| 教师 | `teacher` | `admin123` | 建档、导入素材、纠错、改日期、管理家长账号、看全班 |
| 家长（示例） | `parent` | `123456` | 只能看绑定的孩子的相册；所有写操作都被服务端拒绝 |

- **家长账号由教师在网页「账号管理」页创建**：填账号密码、勾选可见的孩子。家长登录后只能看到这些孩子——不是前端藏按钮，**接口层面就过滤**，越权访问返回 403。
- **首次给孩子建档**：教师进「建立档案」页，上传 1~5 张清晰正面照 + 填名字。之后导入素材就能自动认出这个孩子。
- 会话存本地内存 cookie，**服务重启后需重新登录**（单机可接受）。
- 边界说明：这是**单机软隔离**——网页和接口真实隔离，但同一台电脑上懂技术的人直接翻 `data/` 文件夹挡不住；本地跑通验证足够，真要给出去家长用需要上线 + HTTPS + 正式认证。

## 日常使用（核心流程）

**Mac 最快启动：双击项目根目录的 `启动KidLens.command`**（首次运行会自动建虚拟环境、装依赖），脚本启动服务后会自动打开导入页。关闭弹出的终端窗口即停止服务。

> 地址请固定用 `127.0.0.1:8000`，不要用 `localhost:8000`——本机 localhost 优先解析到 IPv6，可能命中旧服务显示 404。需要换端口可设环境变量 `KIDLENS_PORT`。

手动启动服务后，浏览器打开 **导入页**：

```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

- **导入素材** http://localhost:8000/web/import.html
  整批拖入班级照片/视频 → 选（或留空自动读）活动日期 → AI 人脸识别分拣 → 按孩子归档。
- **相册** http://localhost:8000/web/gallery.html
  左侧选孩子 → 右侧按日期分组翻看 → 点开看大图/视频 → 悬停可改日期。
- **待确认**：认不出的素材进待确认池，在导入页点一下归入某个孩子（照片会顺带学进人脸库，越用越准）。
- **审核台** http://localhost:8000/web/review.html — 周报文案的人工审核（演示看点）。

多人合影的处理：一张照片里有几个孩子，就在这几个孩子的文件夹里各放一份（硬链接，不重复占空间）。
日期来源：导入时手动指定 > 照片 EXIF > 文件修改时间，事后都能在相册里改。

### 备份与恢复（教师专属）

所有素材只存在本机 `data/`，误删或换电脑就没了，建议定期备份：

- **导出**：相册页右上角点「备份相册」，浏览器会下载一个 `kidlens_backup_日期.zip`，内含：
  - `gallery/` — 按孩子+日期整理好的相册本体 + `index.json` 索引
  - `archive/` — 原文件去重库（纠错/改日期要用，别删）
  - `faces/` — 人脸库（删了就得重新建档）
  - `reports/`、`output/` — 周报与集锦
  - `users.json` — 教师/家长账号
  - `恢复说明.txt` — 步骤说明
  - 临时上传副本 `inbox/` 已自动排除，不重复占空间。
- **恢复**：先停服务 → 把 zip 里的内容解压覆盖到项目 `data/` 目录 → 重新启动。相册、人脸库、账号全部还原。
- 备份接口 `GET /api/backup/export` 仅教师可用，家长访问返回 403。

## 技术栈

| 层 | 选型 | 状态 |
|---|---|---|
| 人脸检测/比对 | InsightFace (onnxruntime) | ✅ 已实现 |
| 视频切片/剪辑 | OpenCV（无 ffmpeg 时）/ FFmpeg（有则自动切换） | ✅ 已实现 |
| 存储 | 本地目录 + MD5 去重（`src/core/storage.py`） | ✅ 已实现 |
| 后端 | FastAPI（API + 静态前端一体） | ✅ 已实现 |
| Agent 编排 | LangGraph（interrupt 人工审核中断） | ✅ 已实现 |
| 多模态理解 | 离线模板（默认）/ 云端 VL API / 本地 MLX-VLM | ✅ 三路已实现 |
| 周报存储 | JSON 落盘（`src/db/report_store.py`） | ✅ 已实现 |
| 前端 | 原生 HTML/CSS/JS（零 CDN） | ✅ 已实现 |
| 相册归档 | 按孩子+日期硬链接，EXIF/mtime/手动日期 | ✅ 已实现 |
| 批量导入 | 网页拖拽多文件 → 人脸分拣 → 待确认纠错 | ✅ 已实现 |

> 为什么不装 MinIO：社区版已归档、官方 Docker 镜像下架，且容器常驻吃 4~8GB 内存。
> 展示项目用本地目录抽象一层即可，接口保持同名，将来要换 MinIO 也能无缝替换。

## 目录结构

```
.
├── 说明文档.md              # 原始 PRD
├── MVP开发任务清单.md        # 开发任务拆解
├── config/
│   └── config.yaml          # 阈值 / 路径 / 剪辑参数（全部配置化）
├── src/
│   ├── main.py              # FastAPI 入口（API + 静态前端一体）
│   ├── config.py            # 配置加载
│   ├── api/                 # HTTP 路由（周报 + 相册 + 登录鉴权）
│   │   ├── auth_routes.py   #   登录/登出/会话/家长账号管理 + 鉴权依赖
│   │   ├── gallery_routes.py#   导入/建档/相册/纠错/备份导出（带角色过滤）
│   │   └──                  #     GET /api/backup/export = 一键备份 zip（教师）
│   ├── core/                # 人脸库 / 检测 / 分拣 / 切片 / 集锦 / 归档 / 存储 / VLM
│   │   ├── users.py         #   本地用户存储（教师/家长 + 绑定孩子）
│   │   ├── gallery.py       #   相册归档引擎（按孩子+日期硬链接）
│   │   └── photo_sorter.py  #   照片/视频人脸分拣
│   ├── workflow/            # LangGraph 周报生成 + 人工审核中断
│   ├── db/                  # 周报存储（JSON）
│   └── models/              # 数据模型
├── scripts/
│   └── cli_pipeline.py      # 命令行闭环入口（建档/扫描/集锦/周报）
├── web/                     # 静态前端
│   ├── index.html           #   产品主页（演示看点）
│   ├── login.html           #   登录入口（教师/家长）
│   ├── enroll.html          #   建立孩子档案（教师）
│   ├── users.html           #   家长账号管理（教师）
│   ├── import.html          #   批量导入 + 待确认纠错 ← 教师日常入口
│   ├── gallery.html         #   按孩子/日期相册 ← 家长/教师入口
│   └── review.html          #   周报审核台
├── data/                    # 运行时数据（git 忽略）
│   ├── inbox/               # 拖入原始素材
│   ├── archive/             # MD5 去重原文件
│   ├── gallery/             # 相册：{孩子}/{日期}/ 硬链接
│   ├── faces/               # 人物基准照 + 特征模板
│   ├── reports/             # 周报
│   └── output/              # 切片 / 集锦（演示用）
└── tests/                   # 测试
```

## 环境搭建（用户自行执行）

```bash
# 1. 建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 装依赖（无需 Docker）
pip install -r requirements.txt

# 3. 复制环境变量并填写（可选，keys 用时才填）
cp .env.example .env

# 4. 启动服务
uvicorn src.main:app --reload
```

PyCharm 打开方式：File → Open → 选本目录 → 设置 Python Interpreter 为 `.venv/bin/python` → 将 `src` 标记为 Sources Root。

## 演示主线

**① 建档 → 扫描 → 出集锦**（无需任何外部服务）：

```bash
# 基准照放 data/faces/，视频放 data/inbox/
python scripts/cli_pipeline.py enroll --name 小宝 --images data/faces/xb1.JPG
python scripts/cli_pipeline.py scan  --input "data/inbox/视频.MP4"
python scripts/cli_pipeline.py run   --input "data/inbox/视频.MP4" --person 小宝
```

> 素材要求：目标孩子的脸要够大、清晰（大特写最佳）。抖音/社交平台录屏如果只剩小脸，识别不出来是正常现象——决定因素是人脸像素大小。

**② 生成成长周报**（LangGraph + 人工审核）：

```bash
python scripts/cli_pipeline.py report --person 小宝 --input "data/inbox/视频.MP4"
# 工作流在审核处中断，草稿落盘。审核通过（可改文案）：
python scripts/cli_pipeline.py report --decision approve --edit "改后的文案"
```

VLM 默认用**离线模板**（无需 API key 即可演示）；有 key 时设 `VLM_PROVIDER=cloud` + `OPENAI_API_KEY` 走云端（发送前会裁掉人脸区域保护儿童隐私）。

**③ Web 展示**（一个服务同时提供 API + 前端）：

```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000
# 主页     http://localhost:8000/web/
# 审核台   http://localhost:8000/web/review.html
# API 文档 http://localhost:8000/docs
```

> 前端默认同源相对路径调 API；后端未启动或双击本地 html 打开时，自动降级到内置演示数据，不影响展示。

存储层可直接单测（标准库实现，装不装依赖都能跑）：

```bash
python -c "from src.core.storage import LocalStorage; s=LocalStorage(); print(s.root, s.scan_inbox())"
```
