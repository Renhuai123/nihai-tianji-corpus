# 复现指南 · 自行生成全部中间层

本库不分发视频、音频、关键帧与整集转写（那属于对原视频的再分发，见 README 版权说明）。
但**管线全部开源**——你可以从 B 站公开视频出发，在自己机器上复现每一个中间层。

## 依赖

- `yt-dlp`、`ffmpeg`（下载与音频抽取）
- macOS Vision framework 或 PaddleOCR（字幕带 OCR）
- `mlx-whisper`（探针转写，模型 `mlx-community/whisper-large-v3-turbo`）
- Python 3 + `zhconv`（繁简归一）

## 步骤概要

```bash
# 1. 下载某一讲（1620×1080，格式 30080；音频须显式合并 bestaudio）
yt-dlp -f "30080+bestaudio" "https://www.bilibili.com/video/BV1KJsLekEfA?p=3" -o p03.mp4

# 2. 抽音频（多音轨时显式选中文轨，勿信 ffmpeg 默认）
ffmpeg -i p03.mp4 -map 0:a:0 -ar 16000 -ac 1 p03.wav

# 3. 裁字幕带逐帧 OCR（底部约 18% 高度、2fps），按 bbox 位置直方图剔除水印区
#    相邻帧同文合并为带起止时间码的 cue → subtitle.jsonl

# 4. 探针转写（务必关掉历史条件，否则可能锁进单字循环）
mlx_whisper p03.wav --model mlx-community/whisper-large-v3-turbo \
    --condition-on-previous-text False --output-format srt

# 5. 质检（本目录 gate_check.py，路径按你的环境调整）
python3 gate_check.py --batch <你的转写目录>
```

## 已踩过的坑（都写进了门禁或参数）

1. B 站 `30080` 视频流不含音轨，必须 `+bestaudio` 合并
2. 多音轨视频 ffmpeg 默认抓第一路，可能不是中文轨
3. whisper 的 `condition_on_previous_text=True` 会在长音频上锁进单字叹词循环（整份输出全是「诶」）——先抽 1 分钟样本验证，全量输出叹词占比 >50% 即中止
4. OCR 引擎置信度对自身错误无判别力（错字也给满分），不可作质量指标；质量只认双源交叉一致率
5. 水印与字幕颜色相近且位置多变，按文字过滤必然漏网+误伤，只能按 bbox 位置过滤
6. whisper 输出繁体、字幕为简体，比对前必须繁简归一，否则一致率被严重低估
