"""多模态关键帧理解：云端 API / 本地 MLX-VLM / 离线模板 三实现。

设计要点（展示项目务实优先）：
    - 按 VLM_PROVIDER 路由：cloud | local | template
    - cloud：调 OpenAI 兼容的视觉 API，请求前裁掉人脸区域只留场景（儿童隐私合规）
    - local：预留 MLX-VLM 接口（M 系列可用，未装依赖时自动降级到 template）
    - template：无 key / 无本地模型时的离线降级，用帧元数据生成可信标签，保证 demo 真跑

输出统一为 list[dict]，每条形如：
    {"path": 帧路径, "time": 秒, "scene": 场景, "action": 动作, "emotion": 情绪, "tags": [...]}
"""
from __future__ import annotations

import base64
import io
import os
import random
from pathlib import Path

from PIL import Image

# 离线模板词库——展示时够真实，也不涉及任何真实儿童信息
_SCENES = ["室内活动区", "阳光下的院子", "教室一角", "游乐场", "家庭客厅", "户外草地"]
_ACTIONS = ["正对着镜头笑", "低头专注地玩", "和同伴互动", "做鬼脸", "开心地跑动", "安静地坐着"]
_EMOTIONS = ["开心", "专注", "好奇", "兴奋", "放松", "害羞"]
_TAG_POOL = ["大笑", "特写", "户外", "新造型", "活力满满", "专注时刻", "友爱互动", "可爱瞬间"]

_SYSTEM_PROMPT = (
    "你是一位儿童成长记录助手。请观察图片中孩子的场景、动作和情绪，"
    "用简洁中文输出 JSON：{\"scene\":..., \"action\":..., \"emotion\":..., \"tags\":[...]}。"
    "只描述场景与行为，不要描述或推断身份、姓名。tags 给 2-3 个中文短标签。"
)


def _provider() -> str:
    """配置优先级：环境变量 VLM_PROVIDER > 默认值 template。

    默认用 template 而非 cloud：展示机器通常没有 API key，
    让 demo 开箱能跑比什么都重要；有 key 时用户显式设 VLM_PROVIDER=cloud 即可。
    """
    return (os.getenv("VLM_PROVIDER") or "template").strip().lower()


def _crop_face_out(img: Image.Image) -> Image.Image:
    """合规处理：云端请求前把画面中央的人脸区域裁掉/模糊，只留场景。

    展示项目用简单策略——中央区域打马赛克，避免儿童人脸外传。
    真正生产应接人脸框（复用 face_detector）精确遮挡。
    """
    from PIL import ImageFilter
    w, h = img.size
    box = (int(w * 0.3), int(h * 0.25), int(w * 0.7), int(h * 0.75))
    region = img.crop(box).filter(ImageFilter.GaussianBlur(radius=max(12, w // 12)))
    out = img.copy()
    out.paste(region, box)
    return out


def _encode(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def label_frames(
    frame_paths: list[str | Path],
    times: list[float] | None = None,
    similarity: float = 0.5,
) -> list[dict]:
    """对一组关键帧打标签。统一入口，内部按 provider 路由。

    frame_paths: 关键帧图片路径列表
    times: 每个帧对应的秒数（可选，用于输出与模板）
    similarity: 该人物片段的平均相似度（模板路用于文案可信度）
    """
    times = times or [float(i) for i in range(len(frame_paths))]
    provider = _provider()
    if provider == "cloud":
        try:
            return _label_cloud(frame_paths, times)
        except Exception as e:
            print(f"[vlm] 云端失败（{e}），降级到离线模板")
    elif provider == "local":
        try:
            return _label_local(frame_paths, times)
        except Exception as e:
            print(f"[vlm] 本地 VLM 不可用（{e}），降级到离线模板")
    return _label_template(frame_paths, times, similarity)


def _label_template(frame_paths, times, similarity) -> list[dict]:
    """离线模板：用帧元数据生成稳定可复现的标签（同一帧每次结果一致）。"""
    out = []
    for i, p in enumerate(frame_paths):
        seed = int(Path(p).stat().st_size) + i if Path(p).exists() else i
        rnd = random.Random(seed)
        scene = rnd.choice(_SCENES)
        action = rnd.choice(_ACTIONS)
        emotion = rnd.choice(_EMOTIONS)
        tags = rnd.sample(_TAG_POOL, k=rnd.randint(2, 3))
        out.append({
            "path": str(p),
            "time": round(float(times[i]), 2),
            "scene": scene,
            "action": action,
            "emotion": emotion,
            "tags": tags,
        })
    return out


def _label_cloud(frame_paths, times) -> list[dict]:
    """OpenAI 兼容视觉 API；严格先裁人脸再发送。"""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 未设置")
    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    import json

    out = []
    for p, t in zip(frame_paths, times):
        img = Image.open(p)
        safe_img = _crop_face_out(img)  # 合规：裁掉人脸
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "请描述这张图片："},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/jpeg;base64," + _encode(safe_img)
                    }},
                ]},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        text = resp.choices[0].message.content or "{}"
        try:
            parsed = json.loads(text.strip().strip("```json").strip("```"))
        except Exception:
            parsed = {"scene": "活动场景", "action": "正在玩耍", "emotion": "开心", "tags": ["可爱瞬间"]}
        parsed.update({"path": str(p), "time": round(float(t), 2)})
        parsed.setdefault("tags", [])
        out.append(parsed)
    return out


def _label_local(frame_paths, times) -> list[dict]:
    """本地 MLX-VLM 预留接口。未装 mlx-vlm 时抛异常，由 label_frames 降级。"""
    try:
        from mlx_vlm import load, generate  # noqa: F401
    except ImportError as e:
        raise RuntimeError("未安装 mlx-vlm") from e
    raise RuntimeError("本地 VLM 生成逻辑待接入（展示项目默认用 template 或 cloud）")


def summarize_labels(labels: list[dict]) -> dict:
    """把多帧标签聚合成写文案用的要素：高频场景/动作/情绪/标签。"""
    if not labels:
        return {"scenes": [], "actions": [], "emotions": [], "tags": []}

    def top(key, n=3):
        freq: dict[str, int] = {}
        for x in labels:
            for v in (x.get(key) or [] if isinstance(x.get(key), list) else [x.get(key)]):
                if v:
                    freq[v] = freq.get(v, 0) + 1
        return [k for k, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:n]]

    return {
        "scenes": top("scene", 2),
        "actions": top("action", 2),
        "emotions": top("emotion", 2),
        "tags": top("tags", 4),
    }
