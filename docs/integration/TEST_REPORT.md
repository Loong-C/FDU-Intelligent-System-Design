# 集成验收记录

日期：2026-10-22（Asia/Shanghai）。分支 `integration/motionmuse`。本报告只声明实际执行的验证，不将模拟、静态检查、音频流和真人硬件验收混为一谈。

## 实际环境

- Windows 11 build 26100；Intel Core i7-14700，20 核 / 28 线程；OpenCV 限制 4 线程。
- 项目 `.venv` Python 3.12.9，opencv-python 4.12.0.88 / NumPy 2.2.6 / cv2-enumerate-cameras 1.3.3 / sounddevice 0.5.3；未安装 contrib、MediaPipe runtime 或第二套手部模型。
- 枚举到的摄像头只有 ToDesk Camera / OBS Virtual Camera；没有可用的物理持板/真人测试场景。未把虚拟摄像头当作实测相机。
- 输出流分别检查默认 ToDesk 虚拟输出和 **G733 Gaming Headset / Windows WASAPI（本次索引 24）**。最终定时音频测试用 G733；索引会随设备变化。
- 没有 Jetson、刚性 Marker 板或人工听感验收；不声明实际声学延迟。
- 原官方双手 fixture 已下载，SHA-256：`70cbeb38e198c9862202e0979c21a99b40ca980d3e7b250176c85b1636a40f12`。图片仅留在忽略的 outputs，不分发。

## 自动测试

```powershell
.\.venv\Scripts\python.exe download_models.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
node --check web/app.js
git diff --check
```

| 检查 | 结果 | 范围 |
| --- | --- | --- |
| 原 `test_pipeline.py` | PASS，3 项 | 真 ONNX，双手、21×3、ID、无手、非镜像；文件原样保留 |
| `test_aruco.py` | PASS，4 项 | 真 Marker 解码、多透视、中心 uv、重复 ID、退化、held/超时/恢复、可控时钟 |
| `test_geometry.py` | PASS，3 项 | width−1 镜像、正逆 H、越界保留、绘制/命中一致、flip-u、null/NaN 防护 |
| `test_interaction.py` | PASS，10 项 | 四和弦驻留/裕量、静止/慢扫、上下扫/冷却、丢手/丢板/身份/过期/突跳、10/20/30/60 FPS |
| `test_audio.py` | PASS，5 项 | 元数据、恰好一次、力度、方向、多声部、队列满/过期、初始化失败/关闭 |
| `test_integration.py` | PASS，8 项 | 4 种镜像/布局组合共 1560 合成帧，四和弦/双方向，真 ONNX+Marker 同帧/身份对齐、HTTP/录制/失败隔离 |
| **合计** | **PASS，33 项，无跳过** | 最终命令重复运行约 7 秒；不含硬件性能验收 |
| 模型 SHA-256 | PASS | 两份原模型校验通过 |
| 原安装入口 setup.ps1 | PASS | 最终完整运行，复用固定依赖并校验模型 |
| 原资源保护 | PASS | models/vendor/hand_tracking.py/download_models.py/test_pipeline.py/start.cmd/stop.ps1 对基线无 diff |
| pip check | PASS | No broken requirements found |
| JS 语法、diff 空白检查 | PASS | Node --check / git diff --check |
| Python 3.10 语法兼容扫描 | PASS | 只证明语法，不代表 Jetson 上运行或 ABI 兼容 |
| 预检脚本 | PASS（PC 执行） | `outputs/jetson_preflight.json` 是 Windows 清单，不是 Jetson 实测 |
| Marker 生成 | PASS | 4 张带白边 PNG 写入 outputs/markers |

## 定时软件闭环与测量

```powershell
.\.venv\Scripts\python.exe tools/verify_runtime.py --seconds 32 --mode synthetic --audio sounddevice --device 24 --sample docs/integration/schema-v2.synthetic.json
.\.venv\Scripts\python.exe tools/verify_runtime.py --seconds 62 --mode onnx --audio mock
```

最终原始测量摘要保存于 [measurements.json](measurements.json)，输出报告和每帧录制在其中指明的 outputs 路径。所有结果均是本机软件路径，不是 Jetson 指标。

| 场景 | 结果 |
| --- | --- |
| 32 s 合成手部 + 真 ArUco + G733 音频流 | PASS；951 帧、29.72 FPS（主动限速约 30 FPS）；四和弦与 up/down 均覆盖 |
| 事件/录制一致性 | PASS；53 唯一事件，53 次回调消费，0 重复/丢弃/欠载；951 帧全部录制 |
| 处理耗时 p50 / p95 | 6.03 / 7.59 ms；该场景手部是脚本数据，inference_ms=0 |
| 事件采集时间戳 → 音频回调 p50 / p95 | 7.35 / 11.73 ms；不含实际声学传播/设备输出延迟，不代表人耳听到声音 |
| 62.078 s 真实 ONNX 静态照片 + 生成 Marker | PASS；782 帧、12.60 FPS；全部帧双手和板有效，0 扫弦误触，782 帧录制完整 |
| ONNX 场景处理 p50 / p95 | 86.07 / 98.14 ms；手部推理 p50 68.88 ms，ArUco p50 8.14 ms |

ONNX 测试图像为 640×960，不是 640×480 实时摄像头；CPU 推理速度约 12 FPS，**未证明 ≥20 FPS 目标**。主要开销是双手模型推理，其次是高分辨率 ArUco 和绘制；如现场不足，先降低采集尺寸、测量相机缓冲和音频后端，再考虑 GPU。

`verify_runtime.py` 会因板丢失、手数不符、重复/丢弃、录制缺帧、音频 error 或静态误触而失败；不会仅打印数据后无条件宣布通过。

## 前端 QA

测试路径：`http://127.0.0.1:8766/` → 合成实时演奏 → 开始/停止录制 → 展开调试/切换右手 → 停止服务。

Browser 插件未提供（Browser plugin not available）；按前端测试技能使用已有 Playwright CLI + Chrome，无新增前端依赖。桌面 1440×1080、手机 390×844。

| 检查 | 结果 |
| --- | --- |
| URL / title / 非空页面 | PASS，MotionMuse 幻奏 · FDU 演奏台 |
| 画面、区域、和弦/扫弦、mock 标记和模拟标记 | PASS，同帧 snapshot，无浏览器模型/摄像头 |
| 错误遮罩 / console | PASS，无框架错误，0 errors / 0 warnings |
| 录制按钮 | PASS，开始后显示停止录制及目录；停止后显示已保存，磁盘有 JSONL/CSV/events |
| 调试面板 | PASS，切换 Right #2，21 行坐标与 UV；模型局部三维有明确说明 |
| 手机布局 | PASS，scrollWidth 不超过 viewport，表格在容器内滚动 |
| 停止服务 | PASS，视频、和弦、节点清空，按钮禁用，历史事件仅保留展示 |
| 截图 | PASS，桌面/手机截图在本次 Codex 可视化目录；不提交个人机器路径截图到仓库 |

没有运行 Firefox/Safari 或真实手机硬件；这些为 NOT TESTED。静态扫描确认无 getUserMedia、detectForVideo、@mediapipe、JS Homography 或 AudioContext。

## 过程中的失败与修复

1. `py -0p` 没有登记解释器；找到 PATH 上的 Python 3.12.9，建立项目 venv，setup 增加相同版本入口。原测试照片缺失，通过 README 的官方 URL 下载解决，没有跳过旧测试。
2. 沙箱初次 git fetch 写 FETCH_HEAD、网络下载受限；获准执行作用域明确的 fetch/本地 venv 安装/fixture 下载，均成功。没有用户数据覆盖或强推。
3. HTTP 改造初版遗漏 `return Handler`，首次真实浏览器请求暴露 TypeError；修复后增加 HTTP 路由/控制/图像回归，全部通过。
4. 音频故障注入发现 mock 初始化失败后仍 pump，导致视频退出；增加状态门控，`test_audio_failure_keeps_video_alive` 验证视觉继续、音频 error。
5. 初版在照片外加 100px 边框导致手掌检测尺度变化，只检出一手。改为在原照片四个无手背景角落叠加带白边 Marker，保持原尺度；原照片三项测试未改，融合新测试双手成功。此失败也提示实际缩放会影响检出率。
6. Windows Python 3.12 默认 time.monotonic 粒度令短耗时出现 0/16ms 量化。新增 `timing.py`，采集/逻辑/音频统一高精度 perf_counter 单调时钟，重跑全测试及定时测量；报告采用修复后的结果。
7. UI 断连后展开调试可能重绘缓存节点；清空 latest/选择器并禁用录制，停止状态重新验证。

## 人工硬件验收表（待现场填写）

| 项目 | 本次状态 | 现场须记录 |
| --- | --- | --- |
| 真实 PC 摄像头、刚性板平移/旋转/倾斜 | NOT TESTED | 相机型号、分辨率、距离、角度、光照，固定相对点 UV 漂移 |
| 短遮挡/持续遮挡/重获 | NOT TESTED（合成 PASS） | held/lost 时长、重获是否误发声 |
| 真人四和弦、上下扫、连续 ≥30 s | NOT TESTED | 每种动作实际数、触发、漏检、误触 |
| 真人静止 ≥60 s | NOT TESTED（静态照片 PASS） | 自然手抖/板抖/遮挡下误触数 |
| 人耳可听四和弦与力度 | NOT TESTED（G733 流 PASS） | 实际输出路由、音量、音色、重叠效果 |
| 动作到实际声学输出延迟 | NOT TESTED | 外部同步音视频测量 p50/p95，目标 <200 ms |
| Jetson Xavier NX 及 ≥20 FPS | NOT TESTED | JetPack/L4T/Python/CUDA/OpenCV、功耗/温度、CPU/GPU 后端、FPS 分布 |

已知边界：二维投影不能证明接触；track_id 和左右手分类会受遮挡影响；保守复位可能漏扫；音源是测试合成；B 的公开再分发许可仍需组员确认。本次不合并 main，不改写来源历史。
