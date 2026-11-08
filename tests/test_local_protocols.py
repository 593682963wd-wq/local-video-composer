"""作者：Wangyuan；日期：2026-11-08。职责：多输入解码及输出保持本地协议。"""
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
import engine


class LocalProtocolTests(unittest.TestCase):
    def test_inspector_rejects_url_before_any_child(self):
        with patch.object(engine.subprocess, 'run') as child:
            with self.assertRaisesRegex(ValueError, '本地'):
                engine.inspect_video_info('http://127.0.0.1:9/synthetic.mp4')
            child.assert_not_called()

    def test_second_input_does_not_escape_the_protocol_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            wav = Path(temporary) / 'synthetic.wav'
            with wave.open(str(wav), 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
                stream.writeframes(bytes(16000))
            with self.assertRaisesRegex(ValueError, 'not on whitelist'):
                engine.ff(['-i', wav, '-i', 'http://127.0.0.1:9/second.wav', '-map', '1:a', '-f', 'null', '-'])

    def test_network_output_is_rejected_before_any_child(self):
        with patch.object(engine.subprocess, 'run') as child:
            with self.assertRaisesRegex(ValueError, '本地'):
                engine.ff(['-i', 'synthetic.wav', 'http://127.0.0.1:9/output.wav'])
            child.assert_not_called()


if __name__ == '__main__':
    unittest.main()
