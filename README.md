# 本地短片合成器

保留 3—8 镜头检查、方向与像素比、原生分辨率画布、裁切/完整画面、字幕绘制、现有录音对齐、重复取材检测、SRT/封面/时间线和 MP4 输出。

## 运行与验证

Python 3.11+，FFmpeg/ffprobe，已获使用权的本地字体。

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export VIDEO_FONT=/path/to/your/font.ttf
# FFmpeg 在 PATH 时自动发现，也可显式设置 FFMPEG_BIN / FFPROBE_BIN
python3 cli.py --demo /tmp/composer-demo
python3 -B -m unittest discover -s tests -v
```

`--demo` 仅生成彩色画面与合成音调，不读取素材库、不播放音频。实际输入：工作目录内提供 `shot0.mp4`/`uploaded0.audio` 等文件及 JSON 制作记录，再运行 `python3 cli.py 目录 配置.json`。测试的媒体集成需配置 FFmpeg 和字体，缺失即失败而非假装通过。

## 拆分边界

已删除所有语音生成、模型服务、音乐下载、自动发布与营销文案链路。不含客户素材、个人录音、音乐或字体。只处理显式提供的本地媒体，不能生成数字人或自动配音。

初始数据均为合成样例。运行后用户输入/导出属于用户自己的数据，不能随源码发布。源码采用 MIT 许可证，见 LICENSE；本目录没有携带原仓库历史。

## 2026-11-08 协作修订

- 渲染使用探测到的视频流索引，避免文件首流为音频时选错。
- 相对二进制路径先按启动目录解析再切换工作目录，兼容显式工具位置。

集合根目录 `verify_release.py --project external-local-video-composer` 可复跑测试和包内首次使用示例；Web实际交互的浏览器证据另记。原版本测试数是历史记录，本轮以集合验证报告为准。


### 待发布版联网边界

媒体探测只接受调用方明确指定的本地路径，拒绝网络URL。FFmpeg/ffprobe及音频解码输入只允许本地协议；多输入逐一设置。没有公司接口、模型API或自动下载。程序依赖调用方选择的本地工具和文件；自行替换可执行文件、修改代码或接入外部服务属于新的信任边界。依赖安装可能需要网络，区别于媒体处理运行。
