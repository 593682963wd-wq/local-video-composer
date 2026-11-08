"""作者：Wangyuan；日期：2026-11-08。职责：验证探测与渲染选流一致。"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import engine


class StreamSelectionTests(unittest.TestCase):
    def test_attached_cover_is_not_selected_for_render(self):
        streams = [
            {'index': 0, 'codec_type': 'video', 'disposition': {'attached_pic': 1}, 'width': 100, 'height': 100},
            {'index': 1, 'codec_type': 'video', 'width': 216, 'height': 384, 'duration': '4', 'disposition': {}},
            {'index': 2, 'codec_type': 'audio'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            executable = folder / 'probe'
            executable.touch()
            with patch.object(engine, 'FFPROBE', str(executable)), patch.object(engine.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps({'streams': streams}))):
                info = engine.inspect_video_info(folder / 'synthetic.mp4')
            self.assertEqual(info['stream_index'], 1)
            self.assertEqual((info['width'], info['height']), (216, 384))
            calls = []
            payload = {'product': 'Synthetic demo', 'category': 'sample',
                       'scenes': [{'text': f'Color {i}', 'evidence': f'Synthetic scene {i}', 'audio': True, 'start': .5} for i in range(3)],
                       'story': {'content_kind': 'sequence', 'purpose': 'private', 'question': 'What follows?', 'answer': 'Three colors', 'viewer_action': 'Inspect output', 'reviewed': True}}
            with patch.object(engine, 'FFMPEG', str(executable)), patch.object(engine, 'FONT', str(executable)), \
                    patch.object(engine, 'inspect_video_info', return_value=info), \
                    patch.object(engine, 'audio_seconds', return_value=1.5), \
                    patch.object(engine, 'overlay'), patch.object(engine, 'ff', side_effect=lambda args, *extra: calls.append(args)), \
                    patch('production_gate.validate_media'):
                engine.render(folder, payload)
            filters = [args[args.index('-filter_complex') + 1] for args in calls if '-filter_complex' in args]
            self.assertEqual(len(filters), 3)
            self.assertTrue(all(value.startswith('[0:1]') for value in filters))

    def test_relative_ffmpeg_environment_is_resolved_before_cwd_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'bin').mkdir()
            executable = folder / 'bin' / 'ffmpeg'
            executable.touch()
            env = dict(os.environ, PYTHONPATH=str(Path(engine.__file__).resolve().parent), FFMPEG_BIN='./bin/ffmpeg')
            result = subprocess.run([sys.executable, '-B', '-c', 'import engine;print(engine.FFMPEG)'], cwd=folder, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), executable.resolve())


if __name__ == '__main__':
    unittest.main()
