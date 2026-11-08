"""作者：Wangyuan；日期：2026-10-29。职责：验证真实编码输出与非法媒体边界。"""
import json
import tempfile
import unittest
from pathlib import Path
from cli import demo
from engine import validate_framing, require_duration, validate_sdr_source, inspect_video_info
from production_gate import repeated_seconds, validate_media


class MediaTests(unittest.TestCase):
    def test_framing_rejects_invalid(self):
        for value in [True, -1, float('nan'), float('inf'), 1.1]:
            with self.assertRaises(ValueError): validate_framing('cover', value)
        with self.assertRaises(ValueError): validate_framing('anything', .5)
        self.assertEqual(validate_framing('contain', .5), ('contain', .5))

    def test_duration_and_hdr(self):
        with self.assertRaises(ValueError): require_duration(2, 3, 0)
        with self.assertRaises(ValueError): validate_sdr_source({'color_transfer': 'smpte2084'})

    def test_overlap_union(self):
        self.assertAlmostEqual(repeated_seconds([('a', 0, 5), ('a', 2, 7), ('b', 0, 5)]), 3)
        with self.assertRaises(ValueError): repeated_seconds([('a', 4, 3)])

    def test_renamed_duplicate_media_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for i in range(2): (folder / f'shot{i}.mp4').write_bytes(b'synthetic bytes')
            with self.assertRaises(ValueError):
                validate_media(folder, {'scenes': [{'start': 0}, {'start': 0}]}, [{'duration': 5}, {'duration': 5}])

    def test_real_synthetic_video_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'new'
            result = demo(folder)
            info = inspect_video_info(folder / '成片.mp4')
            self.assertEqual((result['width'], result['height']), (216, 384))
            self.assertAlmostEqual(info['duration'], 6, delta=.2)
            self.assertTrue(info['has_audio'])
            self.assertEqual(len(result['scenes']), 3)
            self.assertIn('BLUE sample', (folder / '字幕.srt').read_text())
            self.assertEqual(json.loads((folder / '时间线.json').read_text())['duration'], 6)
            self.assertGreater((folder / '封面.jpg').stat().st_size, 100)


if __name__ == '__main__':
    unittest.main()
