"""作者：Wangyuan；更新：2026-10-29。职责：本地镜头与已有音频合成，兼容三至八镜头。"""
from pathlib import Path
import json, math, os, re, shutil, subprocess, wave, struct
from typing import Any, Callable, TypedDict
from PIL import Image, ImageDraw, ImageFont
from video_typography import art_font, draw_soft_text, text_lines

ROOT = Path(__file__).resolve().parent
FFMPEG = os.environ.get('FFMPEG_BIN') or shutil.which('ffmpeg') or ''
FFPROBE = os.environ.get('FFPROBE_BIN') or shutil.which('ffprobe')
FFMPEG = str(Path(FFMPEG).resolve()) if FFMPEG else ''
FFPROBE = str(Path(FFPROBE).resolve()) if FFPROBE else None
FFMPEG_THREADS = os.environ.get('FFMPEG_THREADS', '2')
FONT = os.environ.get('VIDEO_FONT') or ''
ROLES = ['远景 · 整体效果', '近景 · 纹路细节', '中景 · 搭配收尾']

def shot_roles(count: int) -> list[str]:
    """验证镜头数并提供拍摄提示；数组长度不证明素材内容独立。"""
    if type(count) is not int or not 3 <= count <= 8:
        raise ValueError('支持3—8个镜头，建议选择5或6个。')
    if count == 3:
        return list(ROLES)
    middle = ['中景 · 配色搭配', '近景 · 纹路细节', '换角度 · 材质变化', '实物 · 对比选择', '空间 · 组合效果', '补充 · 另一处细节']
    return ['远景 · 整体效果', *middle[:count-2], '收尾 · 回到整体']

def run(args, cwd=None):
    p = subprocess.run([str(x) for x in args], cwd=cwd, capture_output=True, text=True, timeout=600)
    if p.returncode:
        raise ValueError(f'媒体处理失败（退出码{p.returncode}）：' + p.stderr[-1800:])
    return p

LOCAL_PROTOCOLS = 'file,pipe,crypto,data'


def _local_media_path(path: Path | str) -> str:
    value = os.fspath(path)
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', value) and not Path(value).drive:
        raise ValueError('只接受明确指定的本地媒体文件，不接受URL或协议地址')
    return str(Path(value).expanduser().resolve())


def ff(args, cwd=None):
    # 多尺度画面叠加时限制过滤图并行，避免自动线程数放大内存占用。
    guarded = []
    for value in args:
        if value == '-i': guarded.extend(['-protocol_whitelist', LOCAL_PROTOCOLS])
        guarded.append(value)
    if args:
        value = os.fspath(args[-1]) if isinstance(args[-1], (str, os.PathLike)) else str(args[-1])
        if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', value) and not Path(value).drive:
            raise ValueError('输出必须是本地文件或标准输出，不接受网络地址')
    return run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-threads', FFMPEG_THREADS, '-filter_threads', '1',
                '-filter_complex_threads', '1', *guarded], cwd)

class VideoInfo(TypedDict):
    """记录显示方向；横屏仍允许上传，是否裁切由画面适配参数决定。"""

    duration: float
    width: int
    height: int
    display_width: int
    display_height: int
    rotation: float
    aspect_ratio: float
    orientation: str
    has_audio: bool
    probe: str
    color_transfer: str
    color_primaries: str
    stream_index: int


def inspect_video_info(path: Path | str) -> VideoInfo:
    """读取实际视频方向与时长；没有 ffprobe 时兼容原 FFmpeg 环境。"""
    path = _local_media_path(path)
    probe = FFPROBE or str(Path(FFMPEG).resolve().with_name('ffprobe'))
    rotation = 0.0
    sample_aspect = 1.0
    color_transfer = color_primaries = 'unknown'
    stream_index = 0
    if Path(probe).is_file():
        result = subprocess.run(
            [probe, '-protocol_whitelist', LOCAL_PROTOCOLS, '-v', 'error', '-show_streams', '-show_format',
             '-of', 'json', str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            raise ValueError('素材无法读取，或不是带画面的视频。请使用 MP4 / MOV。')
        try:
            data = json.loads(result.stdout)
            streams = data.get('streams', [])
            video = next(s for s in streams if s.get('codec_type') == 'video'
                         and not s.get('disposition', {}).get('attached_pic'))
            stream_index = int(video.get('index', 0))
            color_transfer = video.get('color_transfer', 'unknown')
            color_primaries = video.get('color_primaries', 'unknown')
            width, height = int(video['width']), int(video['height'])
            duration = float(video.get('duration')
                             or data.get('format', {}).get('duration'))
            rotation = float(video.get('tags', {}).get('rotate', 0))
            for side_data in video.get('side_data_list', []):
                if 'rotation' in side_data:
                    rotation = float(side_data['rotation'])
            sar = video.get('sample_aspect_ratio', '1:1').split(':')
            if len(sar) == 2 and float(sar[1]) > 0 and float(sar[0]) > 0:
                sample_aspect = float(sar[0]) / float(sar[1])
            has_audio = any(s.get('codec_type') == 'audio' for s in streams)
        except (KeyError, ValueError, TypeError, StopIteration) as exc:
            raise ValueError('素材的视频尺寸或时长无法读取。') from exc
        probe_name = 'ffprobe'
    else:
        result = subprocess.run(
            [FFMPEG, '-hide_banner', '-nostdin', '-protocol_whitelist', LOCAL_PROTOCOLS, '-i', str(path)],
            capture_output=True, text=True, timeout=30,
        )
        duration_match = re.search(
            r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', result.stderr,
        )
        video_line = next((line for line in result.stderr.splitlines()
                           if re.search(r'Stream .*Video:', line) and 'attached pic' not in line), '')
        stream_match = re.search(r'Stream #0:(\d+)', video_line)
        if stream_match:
            stream_index = int(stream_match.group(1))
        color_transfer = next((v for v in ('arib-std-b67', 'smpte2084') if v in video_line), 'unknown')
        color_primaries = 'bt2020' if 'bt2020' in video_line else 'unknown'
        dimensions = re.search(r'\b(\d{2,})x(\d{2,})\b', video_line)
        if not duration_match or not dimensions:
            raise ValueError('素材无法读取，或不是带画面的视频。请使用 MP4 / MOV。')
        duration = (int(duration_match[1]) * 3600 + int(duration_match[2]) * 60
                    + float(duration_match[3]))
        width, height = int(dimensions[1]), int(dimensions[2])
        sar_match = re.search(r'SAR (\d+):(\d+)', video_line)
        if sar_match and int(sar_match[2]):
            sample_aspect = int(sar_match[1]) / int(sar_match[2])
        rotation_match = re.search(r'rotation of (-?[\d.]+)', result.stderr)
        if rotation_match:
            rotation = float(rotation_match[1])
        has_audio = bool(re.search(r'Stream .*Audio:', result.stderr))
        probe_name = 'ffmpeg'
    if width <= 0 or height <= 0 or not math.isfinite(duration):
        raise ValueError('素材的视频尺寸或时长无法读取。')
    if duration < 2 or duration > 120:
        raise ValueError('每个镜头请上传 2—120 秒的视频，建议 8—10 秒。')
    display_width, display_height = round(width * sample_aspect), height
    if round(rotation) % 180 in range(45, 136):
        display_width, display_height = display_height, display_width
    ratio = display_width / display_height
    orientation = 'portrait' if ratio < .95 else 'landscape' if ratio > 1.05 else 'square'
    return VideoInfo(
        duration=duration, width=width, height=height,
        display_width=display_width, display_height=display_height,
        rotation=rotation, aspect_ratio=round(ratio, 6),
        orientation=orientation, has_audio=has_audio, probe=probe_name,
        color_transfer=color_transfer, color_primaries=color_primaries,
        stream_index=stream_index,
    )


def inspect_video(path: Path | str) -> float:
    """保留旧接口的时长返回值，避免已有调用和测试发生不兼容变更。"""
    return inspect_video_info(path)['duration']


def validate_framing(fit: str = 'cover', focus_x: float = .5) -> tuple[str, float]:
    """限制裁切参数，防止非法坐标或用户文本进入 FFmpeg 过滤表达式。"""
    if fit not in ('cover', 'contain'):
        raise ValueError('画面适配请选择 cover（铺满竖屏）或 contain（完整画面）。')
    if isinstance(focus_x, bool):
        raise ValueError('主体左右位置应为0—1之间的数字。')
    try:
        focus = float(focus_x)
    except (TypeError, ValueError) as exc:
        raise ValueError('主体左右位置应为0—1之间的数字。') from exc
    if not math.isfinite(focus) or not 0 <= focus <= 1:
        raise ValueError('主体左右位置应为0—1之间的数字。')
    return fit, focus


def common_portrait_size(infos: list[VideoInfo], zooms: list[float] | None = None) -> tuple[int, int]:
    """选择所有素材都能承担的偶数9:16画布；裁切和主动放大也不升采样。"""
    if not infos:
        raise ValueError('请先提供拍摄素材。')
    zooms = zooms or [1.0] * len(infos)
    if len(zooms) != len(infos) or any(not math.isfinite(z) or not 1 <= z <= 2 for z in zooms):
        raise ValueError('缩放须在1—2倍内。')
    limits = []
    for info, zoom in zip(infos, zooms):
        native_w, native_h = info['width'], info['height']
        if round(info['rotation']) % 180 in range(45, 136):
            native_w, native_h = native_h, native_w
        # 非方形像素改用缩小短轴实现，禁止先拉伸再伪装成原生清晰度。
        factor = min(native_w/info['display_width'], native_h/info['display_height'], 1)
        limits.append(math.floor(min(info['display_width']*factor/18,
                                     info['display_height']*factor/32)/zoom))
    units = min(60, *limits)
    if units < 1:
        raise ValueError('素材尺寸过小，无法制作竖屏视频。')
    return units * 18, units * 32


def validate_sdr_source(info: VideoInfo) -> None:
    """拦截未转换的HDR/广色域输入，防止常规8位导出悄然改变实物色彩。"""
    if info.get('color_transfer') in {'arib-std-b67', 'smpte2084'} or info.get('color_primaries') == 'bt2020':
        raise ValueError('素材为HDR或BT.2020广色域，请先进行专门的HDR转SDR处理并核对颜色；日常剪辑不会直接改写为SDR。')


def require_duration(available: float, required: float, index: int) -> None:
    """素材不足时要求补拍或缩短旁白，不使用末帧冻结补足。"""
    if available + 1e-6 < required:
        raise ValueError(f'第 {index + 1} 段素材不够长：可用 {available:.2f} 秒，需要 {required:.2f} 秒。请补拍或缩短旁白。')


def portrait_filter(fit: str = 'cover', focus_x: float = .5,
                    width: int = 1080, height: int = 1920,
                    focus_y: float = .5, zoom: float = 1.0) -> str:
    """按调用方核验后的画布适配竖屏；保留原接口，日常入口传入原生尺寸。"""
    fit, focus = validate_framing(fit, focus_x)
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise ValueError('输出宽高必须为正偶数。')
    if not math.isfinite(focus_y) or not 0 <= focus_y <= 1:
        raise ValueError('主体上下位置应为0—1之间的数字。')
    if not math.isfinite(zoom) or not 1 <= zoom <= 2:
        raise ValueError('缩放须在1—2倍内。')
    w, h = int(width * zoom // 2) * 2, int(height * zoom // 2) * 2
    square_pixels = r'scale=trunc(iw*min(sar\,1)/2)*2:trunc(ih/max(sar\,1)/2)*2,setsar=1,'
    if fit == 'cover':
        layout = (f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,'
                  f'crop={width}:{height}:(iw-ow)*{focus:.8f}:(ih-oh)*{focus_y:.8f},')
    else:
        layout = (f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                  f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x172026,')
    return square_pixels + layout + 'setsar=1,fps=30,setpts=PTS-STARTPTS'

def audio_seconds(path):
    with wave.open(str(path)) as f:
        return f.getnframes()/f.getframerate()

def overlay(path: Path | str, title: str, text: str, demo: bool = False,
            headline: str = '', caption_style: str = 'serif',
            width: int = 1080, height: int = 1920) -> None:
    """使用艺术字幕；素材来源留在作品说明，画面左上角不再显示标签。"""
    im = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    scale = width / 1080
    font = art_font(caption_style, round((50 if caption_style == 'serif' else 52) * scale))
    lines = text_lines(text, font, round(774 * scale))
    if len(lines) > 4:
        raise ValueError('字幕过长，请缩短介绍')
    y = (1436-72*(len(lines)-1)) * scale
    for i, line in enumerate(lines):
        x = 82 * scale + (774 * scale-font.getlength(line))/2
        draw_soft_text(im, (x, y+72*scale*i), line, font)
    if headline:
        headline_font = art_font(caption_style, round((64 if len(headline)>20 else 84) * scale))
        headline_lines = text_lines(headline, headline_font, round(760 * scale))
        if len(headline_lines) > 2:
            raise ValueError('开头标题过长，请缩短到两行以内。')
        for row, line in enumerate(headline_lines):
            draw_soft_text(im, (90*scale, (380+row*100)*scale), line, headline_font)
    im.save(path)

def make_music(path, seconds):
    """Simple original synthesized chord bed for pipeline demonstration."""
    sr=24000
    chords=[(130.81,164.81,196),(110,130.81,164.81),(87.31,110,130.81),(98,123.47,146.83)]
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
        buf=bytearray()
        for i in range(int(seconds*sr)):
            t=i/sr; chord=chords[int(t/2)%4]; phase=t%2
            env=min(1,phase/.12)*min(1,(2-phase)/.3)
            val=sum(math.sin(2*math.pi*f*t) for f in chord)/3*.13*env
            buf.extend(struct.pack('<h',int(32767*val)))
            if len(buf)>48000: w.writeframes(buf);buf.clear()
        w.writeframes(buf)

def render(folder: Path | str, payload: dict[str, Any],
           progress: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """核验制作记录与真实素材后生成竖屏成片；不足时明确拒绝凑长。"""
    folder=Path(folder)
    if not Path(FFMPEG).is_file(): raise ValueError('未找到 FFmpeg，请设置 FFMPEG_BIN。')
    if not Path(FONT).is_file(): raise ValueError('未找到中文字体，请设置 VIDEO_FONT。')
    from production_gate import validate_story, validate_media
    validate_story(payload)
    scenes=payload['scenes']
    headline = payload.get('headline', '')
    publish_title = payload.get('publish_title', '')
    for value, maximum, name in [(headline, 24, '开头标题'), (publish_title, 80, '发布标题')]:
        if not isinstance(value, str) or len(value) > maximum or any(c in value for c in '\n\r\x00'):
            raise ValueError(f'{name}应为一行，最多{maximum}字。')
    roles = shot_roles(len(scenes))
    source_infos = []
    for i, scene in enumerate(scenes):
        text=scene['text'].strip()
        if not 2<=len(text)<=48 or any(c in text for c in '\n\r\x00'):
            raise ValueError(f'第 {i+1} 段旁白请写成 2—48 字的一行。')
        validate_framing(scene.get('fit', payload.get('fit', 'cover')),
                        scene.get('focus_x', payload.get('focus_x', .5)))
        source_infos.append(inspect_video_info(folder/f'shot{i}.mp4'))
    for source_info in source_infos:
        validate_sdr_source(source_info)
    validate_media(folder, payload, source_infos)
    width, height = common_portrait_size(source_infos)
    all_durations=[]; warnings=[]; timeline=[]
    natural_durations=None
    uploaded=[bool(s.get('audio')) for s in scenes]
    if not all(uploaded):
        raise ValueError('每段必须提供本地录音，本引擎不包含语音生成接口。')

    durations = []
    for i, scene in enumerate(scenes):
        wav = folder / f'voice{i}.wav'
        if scene.get('audio'):
            ff(['-i', folder/f'uploaded{i}.audio', '-vn', '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', wav])
        duration = natural_durations[i] if natural_durations is not None else max(2.0, audio_seconds(wav)+.15)
        if not math.isfinite(duration) or duration <= 0 or duration > 18:
            raise ValueError(f'第 {i+1} 段旁白时长须为0—18秒，请缩短或重新录制。')
        start = float(scene.get('start', .5))
        vd = source_infos[i]['duration']
        if not math.isfinite(start) or start < 0 or start >= vd:
            raise ValueError(f'第 {i+1} 段起点超出素材时长。')
        require_duration(vd-start, duration, i)
        durations.append(duration)
    validate_media(folder, payload, source_infos, durations=durations)
    for i, s in enumerate(scenes):
        text = s['text'].strip()
        video, wav = folder/f'shot{i}.mp4', folder/f'voice{i}.wav'
        source_info = source_infos[i]
        duration, start = durations[i], float(s.get('start', .5))
        progress(f'正在生成第 {i+1}/{len(scenes)} 段旁白与镜头')
        overlay(folder/f'overlay{i}.png', payload['product'],text,payload.get('demo',False),
                headline=headline if i == 0 else '', caption_style=payload.get('caption_style','serif'),
                width=width, height=height)
        fit, focus = validate_framing(s.get('fit', payload.get('fit', 'cover')),
                                     s.get('focus_x', payload.get('focus_x', .5)))
        if source_info['orientation'] == 'landscape' and fit == 'cover':
            warnings.append(f'第{i+1}段为横屏，已按主体左右位置裁切；请检查主体，后续请竖持拍摄。')
        filters=(f'[0:{source_info["stream_index"]}]{portrait_filter(fit, focus, width, height)}[v];[v][1:v]overlay=0:0:format=auto[out];'
                 f'[2:a]apad,atrim=duration={duration},asetpts=PTS-STARTPTS[a]')
        ff(['-ss',start,'-i',video,'-i',folder/f'overlay{i}.png','-i',wav,'-filter_complex',filters,
            '-map','[out]','-map','[a]','-t',duration,'-c:v','libx264','-preset','veryfast','-crf','22',
            '-threads',FFMPEG_THREADS,'-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',folder/f'part{i}.mp4'])
        timeline.append(dict(role=roles[i],text=text,start=sum(all_durations),duration=duration,
                             source_start=start,fit=fit,focus_x=focus,source_metadata=source_info))
        all_durations.append(duration)
    (folder/'concat.txt').write_text(''.join(f"file 'part{i}.mp4'\n" for i in range(len(scenes))))
    progress('正在合并画面、字幕与背景音乐')
    ff(['-f','concat','-safe','0','-i','concat.txt','-c','copy','joined.mp4'],folder)
    total=sum(all_durations)
    ff(['-i',folder/'joined.mp4','-c','copy','-movflags','+faststart',folder/'成片.mp4'])
    ff(['-i',folder/'成片.mp4','-frames:v','1',folder/'封面.jpg'])
    def stamp(t):
        ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    (folder/'字幕.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(s["start"])} --> {stamp(s["start"]+s["duration"])}\n{s["text"]}' for i,s in enumerate(timeline)),encoding='utf-8')
    result=dict(width=width,height=height,duration=round(total,2),warnings=warnings,scenes=timeline,validation='合成完成；尚需人工预览与真实门店试拍验收')
    (folder/'时间线.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    progress('已生成，请预览后下载')
    return result
