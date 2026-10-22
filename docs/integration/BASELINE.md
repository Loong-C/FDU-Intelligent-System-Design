# 集成基线与来源审计

冻结日期：2026-10-22（Asia/Shanghai）。工作分支：`integration/motionmuse`。

| 来源 | 实际 main SHA | 核实方式 |
| --- | --- | --- |
| A · Loong-C/FDU-Intelligent-System-Design | `15d213948fba422511767645f78bb7f7a9c016e1` | 本地 `git fetch origin`、`git rev-parse HEAD origin/main` |
| B · SMF-an/MotionMuse | `2426ce10a8bc943148f62a9004e819000a7879f6` | GitHub API main 及固定 SHA 源码读取 |

二者与任务书基线相同，无新增上游差异。工作树最初干净。未合并无关 Git 历史，未修改 B，未复制其服务器、MediaPipe 模型、uv.lock 或网页运行时。

## 原始运行与接口

- A：Python 3.12，`setup.ps1` → `start.cmd` 或 `python app.py`，loopback :8765。`HandTracker.process(bgr, timestamp)` 返回 display/packet，镜像显示坐标；21×3 像素、归一化和手部局部米坐标。HTTP `/api/landmarks`、`/frame.jpg`、录制和 shutdown。JSONL 所有帧，CSV 每节点一行。
- A 依赖：opencv-python 4.12.0.88、numpy 2.2.6、cv2-enumerate-cameras 1.3.3；Zoo 包装类和两个 ONNX 已入库。保留 models、vendor 和三个原回归测试。
- B：Python ≥3.13、uv、MediaPipe ≥1.0.1、opencv-python ≥5.0.0.93；`uv run python src/aruco_server.py` :8000 提供另一套摄像头及 MJPEG；网页另载 MediaPipe JS/WASM。旧 Python 原型依赖标定文件、视频和手模型。

## 查明的问题与处理

- 本机为 Windows、PATH 中 Python 3.12.9（Anaconda），`py -0p` 无登记解释器；setup 增加 PATH 中严格 3.12 的后备入口，在项目 `.venv` 内安装，不修改全局环境。
- 原测试照片缺失：按原 README 下载 Google 官方 woman_hands.jpg 到忽略的 `outputs/test_hands.jpg`，不删除、不弱化测试。
- A 的 README 克隆地址为旧上游；start.ps1 只识别 schema 1；摄像头模块强制 Windows 导入。分别修复并保留旧接口。
- B 的网页把 Right 用作 fret，且 bilinear 绘制与 Homography 命中不一致；统一解剖学 Left 和弦 / Right 扫弦，所有区域用 Python 的同一 H 及逆矩阵。
- B 的 ArUco 计算 H 却只返回中心四边形；扩展为原始 marker 角点、H/H^-1、时间与原因。held 仅显示、绝不演奏。
- B 无真正的事件驱动音频；新增本进程非阻塞队列及可替换音频后端，浏览器只展示历史。
- 原 README 的 C270/FPS 报告属于原作者机器，不能视为本次集成或 Jetson 实测。

## 署名和授权

B 原作者 / 维护者为 GitHub **SMF-an** 及其仓库贡献者。审阅时根目录没有公开 LICENSE；以下迁移/参考仅用于任务指定的组内集成，对外重新发布前须由成员确认授权。没有为 B 的代码添加新许可证。

| 本仓库文件 | 来源与变化 |
| --- | --- |
| `aruco_tracking.py` | 改编 B `src/aruco_tracking.py` 的 DICT_4X4_50、ID 排列、凸性/面积校验、valid/held/lost；新增矩阵、可控时间和失效防护 |
| `instrument_geometry.py` | 参考 B `src/board_geometry.py` 的区域尺寸，新实现镜像、投影和统一布局 |
| `instrument_logic.py` | 参考 B `src/hand_tracking_board.py` 与 `web/app.html` 的四和弦/上下扫概念；新实现时间驻留、轨迹状态机、异常复位 |
| `web/index.html` | 保留 A 调试/录制能力，参考 B `web/app.html` 的薄荷绿/琥珀色演奏台视觉语言；重写为无模型、离线 UI |
| `app.py`, `example_client.py`, 启动脚本 | A 增量修改，原接口和推理后端保留 |
| `audio_engine.py`, `pipeline.py`, `camera_sources.py`, 辅助脚本、新测试和文档 | 本次新实现 |
| `hand_tracking.py`, `models/`, `vendor/`, `download_models.py`, `tests/test_pipeline.py` | A 原样保留（官方 Zoo 来源及 Apache-2.0 文本仍在 vendor） |

源链接：[A](https://github.com/Loong-C/FDU-Intelligent-System-Design/tree/15d213948fba422511767645f78bb7f7a9c016e1)、[B](https://github.com/SMF-an/MotionMuse/tree/2426ce10a8bc943148f62a9004e819000a7879f6)。音源由数学振荡器生成，不复制网络采样；详见 `assets/audio/README.md`。

最终测试、实测环境和未测项见 `TEST_REPORT.md`，部署差异见 `JETSON.md`。

## 最终文件清单补充

| 文件 | 归属 |
| --- | --- |
| `.gitignore` | A，追加 Jetson venv 忽略 |
| `README.md` | A，重写集成启动与验证说明，修正远端地址和旧性能声明 |
| `requirements.txt` | A，固定 PC 栈、限定 Windows 枚举、加入音频 |
| `requirements-jetson.txt` | 新实现，候选环境，明确未在设备验证 |
| `setup.ps1` | A，支持 PATH 的 Python 3.12 |
| `start.ps1` | A，识别 schema v2 已运行服务 |
| `app.py` | A，融合调度、兼容 HTTP、原子快照、平台入口 |
| `example_client.py` | A，保留旧输出并展示新增 UV |
| `aruco_tracking.py` | B 改编，见上表 |
| `instrument_geometry.py` | 新实现，区域设计参考 B |
| `instrument_logic.py` | 新实现，四和弦/上下扫概念参考 B |
| `pipeline.py` | 新实现，同帧融合和叠加 |
| `timing.py` | 新实现，共享高精度单调时钟 |
| `audio_engine.py` | 新实现，PortAudio/mock、多声部合成、去重与有界队列 |
| `camera_sources.py` | 新实现，复用 A Windows 选择规则，新增 Linux 隔离 |
| `recording.py` | 新实现，保留 A 列格式的异步录制 |
| `synthetic_input.py` | 新实现，明确标记的脚本手部/生成 Marker |
| `generate_markers.py` | 新实现，可打印 Marker 和白边 |
| `web/index.html` | A 改造，参考 B 演奏台视觉语言 |
| `web/style.css` | 新实现，离线样式及响应式布局 |
| `web/app.js` | 新实现，保留 A 调试功能，无推理/H/音频消费 |
| `assets/audio/README.md` | 新文档，合成音源归属及播放说明 |
| `tests/__init__.py`, `tests/helpers.py` | 新测试支持 |
| `tests/test_aruco.py` | 新合成定位测试 |
| `tests/test_geometry.py` | 新投影/镜像/区域一致性测试 |
| `tests/test_interaction.py` | 新时序轨迹/恢复测试 |
| `tests/test_audio.py` | 新音频 mock/去重/有界队列测试 |
| `tests/test_integration.py` | 新真实 ONNX+Marker、HTTP、录制和完整模拟链路测试 |
| `tools/verify_runtime.py` | 新可重复软件运行及测量脚本 |
| `tools/jetson_preflight.py` | 新只读环境预检脚本 |
| `docs/integration/BASELINE.md`, `API.md`, `JETSON.md`, `TEST_REPORT.md` | 新交付文档 |
| `docs/integration/schema-v2.synthetic.json` | 本次真实运行输出的完整模拟示例 |
| `docs/integration/measurements.json` | 本次测量摘要，明确区分模拟与实机 |

`start.cmd`、`stop.ps1`、两个模型、vendor、hand_tracking.py、download_models.py 和原 tests/test_pipeline.py 未修改。
