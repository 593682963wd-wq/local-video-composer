"""作者：Wangyuan；日期：2026-10-29。职责：本地合成入口与完全合成的端到端样例。"""
from __future__ import annotations
import argparse
import json
import math
import struct
import wave
from pathlib import Path
import engine


def demo(folder: Path) -> dict:
    """只在新目录生成三段彩色视频和合成音调，随后实际编码输出。"""
    folder.mkdir(parents=True, exist_ok=False)
    scenes = []
    for i, color in enumerate(['red', 'green', 'blue']):
        engine.ff(['-f', 'lavfi', '-i', f'color=c={color}:s=216x384:r=30:d=4',
                   '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', folder / f'shot{i}.mp4'])
        with wave.open(str(folder / f'uploaded{i}.audio'), 'wb') as out:
            out.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            out.writeframes(b''.join(struct.pack('<h', int(1000 * math.sin(2 * math.pi * (220+i*110) * n / 24000))) for n in range(36000)))
        scenes.append(dict(text=f'{color.upper()} sample', evidence=f'Synthetic {color} color field', audio=True, start=.5))
    payload = dict(product='Synthetic demo', category='sample', scenes=scenes,
                   story=dict(content_kind='sequence', purpose='private', question='Which color follows?',
                              answer='Red green blue', viewer_action='Inspect the output', reviewed=True))
    (folder / 'example.json').write_text(json.dumps(payload, indent=2))
    return engine.render(folder, payload)


def main() -> None:
    """所有媒体路径由调用者显式指定，不扫描原素材目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?')
    parser.add_argument('config', nargs='?')
    parser.add_argument('--demo', type=Path)
    args = parser.parse_args()
    try:
        if args.demo:
            result = demo(args.demo)
        elif args.folder and args.config:
            result = engine.render(Path(args.folder), json.loads(Path(args.config).read_text()))
        else:
            raise ValueError('提供工作目录与配置 JSON，或 --demo 新目录')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
