# MotionMuse 幻奏 · FDU 智能系统设计

本地视觉乐器：**OpenCV Zoo 双手检测 → ArUco 板面坐标 → 左手 C/G/Am/F 和弦 → 右手上下扫事件 → 本地音频**。浏览器显示同帧骨架、板面、演奏状态和性能，支持 JSONL/CSV 录制。

一个摄像头、一个手部推理后端和一个动作状态机。核心运行无需外网，浏览器不运行 MediaPipe JS。保留 A 的 ONNX、包装类、启动脚本、原回归和 HTTP 路径。两源版本、署名、文件归属见 [BASELINE](docs/integration/BASELINE.md)。

**验证边界：** Windows Python 3.12 自动化、真实 ONNX 照片回归、合成演奏闭环和 PortAudio 输出流已验证。真人持板/物理摄像头、人工听感和 Jetson 实机验收尚未完成，见 [测试报告](docs/integration/TEST_REPORT.md)。合成演示不是硬件性能基准。

## Windows 首次安装

```powershell
git clone https://github.com/Loong-C/FDU-Intelligent-System-Design.git
cd FDU-Intelligent-System-Design
git switch integration/motionmuse
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\start.cmd
```

需要 Python 3.12（PATH 或 py 启动器登记）。setup 仅在项目 `.venv` 安装依赖并验证两份 ONNX SHA-256。PC 固定 OpenCV 4.12.0.88 / NumPy 2.2.6；此 wheel 已有 ArUco，不再安装 contrib。音频新增 sounddevice 0.5.3。

打开 [本地演奏台](http://127.0.0.1:8765/)。默认镜像、640×480，优先 C270，Windows 依次尝试 DSHOW/MSMF。虚拟相机会参与枚举，应选择实际设备。

```powershell
.\.venv\Scripts\python.exe app.py --list-cameras
.\.venv\Scripts\python.exe app.py --camera 0 --backend msmf
.\.venv\Scripts\python.exe app.py --no-mirror
```

`start.cmd` 继续调用 `start.ps1` 在后台启动并打开浏览器。关闭网页不会停服务；点击“停止服务”、Ctrl+C（前台）或执行 `powershell -ExecutionPolicy Bypass -File .\stop.ps1` 释放设备。日志：`outputs/server.stderr.log`。

## 打印和演奏

```powershell
.\.venv\Scripts\python.exe generate_markers.py
```

打印 `outputs/markers/marker_0.png` 至 `marker_3.png`，保留白边，不镜像打印。四个中心固定在同一刚性平板：

```text
ID 0 ---------------- ID 1
          交互平面
ID 2 ---------------- ID 3
```

让四个 Marker 完整进入画面，确认 **VALID**。解剖学左手放在 C/G/Am/F 区域，驻留约 100 ms；右手食指从扫弦中线上方穿到下方发下扫，反向发上扫。四和弦采用区域选择，不是真实吉他指法识别。音色为代码生成的测试音色，可衰减重叠；不是最终吉他采样。

默认和弦区 u=.04–.60，扫弦区 u=.68–.90。朝向不合适时用 `--layout flip-u` 翻转区域，**不交换左右手标签**。短时遮挡最多保持 .25 秒供显示；HELD/LOST 或缺少新鲜左手时均不发新音符。重获后重新驻留、观察扫弦一侧。

UV 是二维成像投影，不表示手指接触板面。原模型 z/world_m 是手部局部估计，不是到板子的厘米距离。

## 音频检查与无摄像头演练

```powershell
.\.venv\Scripts\python.exe audio_engine.py --list-devices
.\.venv\Scripts\python.exe audio_engine.py
# 指定实际输出设备名称或当前枚举索引
.\.venv\Scripts\python.exe app.py --audio-device "G733 Windows WASAPI"

# 明确标记的合成演示，无摄像头，默认 mock 不发声
.\.venv\Scripts\python.exe app.py --demo
# 合成轨迹驱动真实音频输出
.\.venv\Scripts\python.exe app.py --demo --audio sounddevice
# 关闭声音，视觉继续
.\.venv\Scripts\python.exe app.py --audio off
```

初始化失败显示 `audio_status=error` 和原因，视觉继续；mock/disabled 不代表实际发声。事件在本进程消费，浏览器只显示历史。通过 `--interaction-config config.json` 可覆盖 [InteractionConfig](instrument_logic.py)，例如 `{"chord_dwell_s":0.12,"cooldown_s":0.18}`。阈值使用秒和 UV/s，不使用连续帧数。默认保守复位可能漏掉极快/遮挡动作，应实测后调整。

## 接口与录制

`GET /api/landmarks` 仍可供 `example_client.py` 使用，旧字段保留并新增 schema v2 的板面、21×2 UV、交互和音频数据。见 [API / 数据流](docs/integration/API.md) 及 [完整模拟 JSON](docs/integration/schema-v2.synthetic.json)。

```powershell
.\.venv\Scripts\python.exe example_client.py
```

点击“开始录制/停止录制”，保存到 `outputs/日期_时间_微秒/`：

- `landmarks.jsonl`：所有处理帧，含无手帧及完整 instrument/interaction。
- `landmarks.csv`：原列保留，追加 instrument_u/v；无投影留空。
- `events.jsonl`：每个新 event_id 一条。

独立写线程和有界队列，磁盘失败/积压显式报告。`outputs/` 全部忽略，不提交照片、视频或日志。调试面板保留节点表及 XY/XZ 局部投影。网页使用 `/api/snapshot` 获取同一帧图像与状态，原 `/frame.jpg` 保留。

## 可重复验证

先下载原回归必需的 Google 官方双手照片（不随仓库分发）：

```powershell
New-Item -ItemType Directory -Force outputs | Out-Null
Invoke-WebRequest https://storage.googleapis.com/mediapipe-tasks/hand_landmarker/woman_hands.jpg -OutFile outputs/test_hands.jpg
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools/verify_runtime.py --seconds 32 --mode synthetic --audio mock
.\.venv\Scripts\python.exe tools/verify_runtime.py --seconds 32 --mode synthetic --audio sounddevice
.\.venv\Scripts\python.exe tools/verify_runtime.py --seconds 62 --mode onnx --audio mock
```

前两种运行使用脚本手部 + 真 ArUco；第三种用真实 ONNX 识别静态照片及生成的 Marker，检查一分钟静止误触。报告在各录制目录的 `runtime_report.json`。原 `tests/test_pipeline.py` 三项测试未删除或跳过。照片来源：[Google 官方手部示例](https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/hand_landmarker/python/hand_landmarker.ipynb)。

## Jetson Xavier NX

参阅 [JETSON](docs/integration/JETSON.md)。Linux 摄像头隔离到 V4L2/GStreamer，不强制导入 Windows 枚举；提供候选 `requirements-jetson.txt` 和只读 `tools/jetson_preflight.py`。不假设 PC wheel/Python 3.12 可直接移植。≥20 FPS 与 <200 ms 是尚未实测的目标。

默认 loopback；远程观看优先 SSH 转发。显式 `--host` 开启局域网查看，远端控制还需 `--allow-remote-controls`。服务无认证，不在公网暴露。

## 来源和限制

Zoo 固定 `47534e27c9851bb1128ccc0102f1145e27f23f98`，Apache-2.0 文本和原署名在 `vendor/opencv_zoo_runtime/`。模型校验：

```text
palm_detection_mediapipe_2023feb.onnx
78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c
handpose_estimation_mediapipe_2023feb.onnx
db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c
```

MotionMuse 的 ArUco、布局、交互设计与视觉语言来源于 SMF-an 及原贡献者；B 未声明公开许可证，本次按组内任务整合，**对外重新发布前由成员确认授权**。未替他人代码声明新许可证。音源见 [assets/audio](assets/audio/README.md)。

真人遮挡、左右手交叉、倾斜、反光、低光及高速运动仍需实测；track_id 不是永久身份。原 README 的 C270/FPS 成绩属于原作者环境，本次不沿用为集成验收结果。
