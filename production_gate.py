"""作者：Wangyuan；日期：2026-10-29。
职责：在本地视频渲染前检查制作记录、素材边界及重复取材。
语义、色差、听感仍由逐镜审看决定，程序不假装能理解画面。
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

CONTENT_KINDS = {"sequence", "comparison", "tutorial"}
EMPTY_LINES = set()


def _text(value: Any, name: str, limit: int = 100) -> str:
    """缺少具体记录时立即提示，避免空白或占位内容进入旁白。"""
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= limit:
        raise ValueError(f"{name}请填写2—{limit}字的具体内容。")
    if any(mark in value for mark in ("待填写", "待补充", "待确认", "TODO", "\x00")):
        raise ValueError(f"{name}还留有占位内容，请核对原片后填写。")
    return value.strip()


def validate_story(payload: dict[str, Any]) -> None:
    """检查逐镜人工审核记录齐全；不将填写记录当作营销效果验收。"""
    story = payload.get("story")
    if not isinstance(story, dict):
        raise ValueError("先完成制作检查：今天的问题、一句话答案、观众下一步与逐镜画面证据。")
    if story.get("content_kind") not in CONTENT_KINDS:
        raise ValueError("请选择 sequence、comparison 或 tutorial。")
    if story.get("purpose") not in {"public", "private"}:
        raise ValueError("请选择public 或 private。")
    for key, label in (("question", "今天的问题"), ("answer", "一句话答案"),
                       ("viewer_action", "观众下一步得到什么")):
        _text(story.get(key), label)
    if story.get("reviewed") is not True:
        raise ValueError("请逐镜核对：问题有答案、每句有画面支持，再勾选制作检查。")
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or not 3 <= len(scenes) <= 8:
        raise ValueError("请提供3—8段真实镜头；缺镜头时先补拍，不要复制凑数。")
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"第{i}段镜头信息格式不正确。")
        _text(scene.get("evidence"), f"第{i}段实际能看见的内容")
        text = _text(scene.get("text"), f"第{i}段旁白", 48)
        normalized = "".join(c for c in text if c.isalnum())
        if normalized in EMPTY_LINES:
            raise ValueError(f"第{i}段只有泛泛提示，请说出画面中的具体选择或观察。")


def repeated_seconds(intervals: list[tuple[str, float, float]]) -> float:
    """按原文件指纹合并时间区间，识别复制文件改名后的重复取材。"""
    grouped: dict[str, list[tuple[float, float]]] = {}
    total = 0.0
    for source, start, end in intervals:
        if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
            raise ValueError("取材时间必须是有限数值，且终点晚于起点。")
        grouped.setdefault(source, []).append((start, end))
        total += end - start
    unique = 0.0
    for spans in grouped.values():
        merged: list[list[float]] = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(end, merged[-1][1])
            else:
                merged.append([start, end])
        unique += sum(end - start for start, end in merged)
    return max(0.0, total - unique)


def validate_media(folder: Path, payload: dict[str, Any], infos: list[dict[str, Any]],
                   durations: list[float] | None = None) -> dict[str, Any]:
    """配音前查无效原片，配音后用实际时长拒绝冻结和重复画面。"""
    scenes = payload["scenes"]
    if len(infos) != len(scenes) or (durations is not None and len(durations) != len(scenes)):
        raise ValueError("镜头、媒体信息与旁白数量不一致。")
    intervals: list[tuple[str, float, float]] = []
    starts: set[tuple[str, float]] = set()
    for i, (scene, info) in enumerate(zip(scenes, infos, strict=True)):
        try:
            if isinstance(scene.get("start", .5), bool):
                raise ValueError("布尔值不是时间")
            start = float(scene.get("start", .5))
            available = float(info["duration"]) - start
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"第{i + 1}段剪辑起点或原片时长无效。") from exc
        if not math.isfinite(start) or start < 0 or not math.isfinite(available) or available <= 0:
            raise ValueError(f"第{i + 1}段起点已经超出原片，请重新选段或补拍。")
        hasher = hashlib.sha256()
        with (Path(folder) / f"shot{i}.mp4").open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        # 配音前即可阻止同一文件同一起点反复上传；其余重叠等真实旁白长度确定再查。
        key = (digest, round(start, 3))
        if key in starts:
            raise ValueError(f"第{i + 1}段重复了同一原片的同一起点，请换一个有效角度。")
        starts.add(key)
        if durations is not None:
            duration = float(durations[i])
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"第{i + 1}段旁白时长无效。")
            if duration > available + 1 / 30:
                raise ValueError(f"第{i + 1}段仅剩{available:.2f}秒，旁白需要{duration:.2f}秒；"
                                 "请缩短这句或补拍，不能冻结画面凑长。")
            intervals.append((digest, start, start + duration))
    repeated = repeated_seconds(intervals) if intervals else 0.0
    if repeated > .10:
        raise ValueError(f"发现约{repeated:.2f}秒重复画面，请替换重复段或缩短成片。")
    return {"source_count": len({key[0] for key in starts}), "repeated_seconds": round(repeated, 3),
            "timing_checked": durations is not None, "semantic_review": "制作人逐镜记录，程序未识别画面"}
