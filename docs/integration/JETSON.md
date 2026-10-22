# Jetson Xavier NX 部署探路

**本次无 Jetson 实机：硬件部署、CSI/USB 相机、CUDA 推理、ALSA/USB 音箱、≥20 FPS 和 <200 ms 声学延迟均为 NOT TESTED。以下为可复现候选步骤，不是已完成部署的声明。**

## 先盘点，后选择环境

NVIDIA 官方 [JetPack 5.1.2](https://developer.nvidia.com/embedded/jetpack-sdk-512) 页面明确包含 Xavier NX，基于 L4T 35.4.1 / Ubuntu 20.04。它是本指南的参考基线，不表示当前设备版本或最新版本。不要把面向其他 Jetson 代际的 JetPack 镜像直接刷到 NX，也不要为此任务自动刷机。

运行（仅读取信息，不安装软件）：

```bash
python3 tools/jetson_preflight.py
cat outputs/jetson_preflight.json
cat /etc/nv_tegra_release
cat /etc/os-release
python3 --version
nvcc --version
dpkg-query -W nvidia-jetpack nvidia-l4t-core libnvinfer8
v4l2-ctl --list-devices
aplay -l
```

预检记录系统/Python、CUDA/TensorRT 包、OpenCV 构建选项、ArUco、CUDA 设备、ONNX 空白帧推理和声卡。命令/组件不存在会明确记录 unavailable/error。空白推理 PASS 仍需官方手照片回归；声卡枚举不代表播放成功。

2026-10-22 已核对 [NVIDIA skills 目录](https://github.com/NVIDIA/skills/blob/main/skills.sh.json)，存在 jetson-print-device-info、jetson-diagnostic 等设备探路工具；本次没有安装或修改 Agent 技能。现有只读预检脚本足以准备后续验收。

## Python / OpenCV 硬门槛

应用候选最低 Python 3.10（PC 验证 3.12.9），需要 `cv2.aruco.ArucoDetector`、DNN ONNX 和摄像头后端。Ubuntu 20.04 常见系统 Python 不满足此候选版本；请使用设备已有的独立 Python 3.10+，或按组织环境流程准备，**不替换系统 python3**。

不要在 Jetson 直接运行 PC requirements，也不要用 pip wheel 覆盖含 GStreamer/CUDA 的系统 cv2。不可在一个环境中同时安装 opencv-python/opencv-contrib-python。先尝试与选定解释器匹配的现有 OpenCV，验证：

```bash
python3.10 -m venv --system-site-packages .venv-jetson
. .venv-jetson/bin/activate
python -m pip install -r requirements-jetson.txt
python -c "import cv2; print(cv2.__version__); print(hasattr(cv2.aruco, 'ArucoDetector')); print(cv2.getBuildInformation())"
python download_models.py
python tools/jetson_preflight.py
```

如果现有 cv2 缺失/ABI 不匹配，使用专用环境编译候选 OpenCV 4.10.0（仅 CPU+DNN+相机，先保证正确性）。这些构建命令 **NOT TESTED on NX**；先满足 Python 3.10 开发头和 venv 能力：

```bash
sudo apt-get update
sudo apt-get install build-essential cmake git pkg-config libjpeg-dev libpng-dev libtiff-dev \
  libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libportaudio2 portaudio19-dev
python3.10 -m venv .venv-jetson
. .venv-jetson/bin/activate
python -m pip install -r requirements-jetson.txt
git clone --branch 4.10.0 --depth 1 https://github.com/opencv/opencv.git outputs/opencv-4.10.0
cmake -S outputs/opencv-4.10.0 -B outputs/opencv-build \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$VIRTUAL_ENV" \
  -DPYTHON3_EXECUTABLE="$VIRTUAL_ENV/bin/python" \
  -DPYTHON3_PACKAGES_PATH="$VIRTUAL_ENV/lib/python3.10/site-packages" \
  -DPYTHON3_NUMPY_INCLUDE_DIRS="$(python -c 'import numpy; print(numpy.get_include())')" \
  -DBUILD_opencv_python3=ON -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF \
  -DBUILD_EXAMPLES=OFF -DWITH_GSTREAMER=ON -DWITH_V4L=ON -DWITH_CUDA=OFF
cmake --build outputs/opencv-build -j2
cmake --install outputs/opencv-build
python tools/jetson_preflight.py
```

若使用 Python 3.11/3.12，请相应修改 packages 路径和 NumPy 兼容版本。无 sudo 安装到 venv；若 CMake 找错解释器，先修复配置，不拷贝未知 ABI 的 cv2.so。ARM64 构建时间、内存与温度依设备而定，`-j2` 是保守起点。OpenCV 的 CUDA/TensorRT 是后续独立优化路径，本次没有把存在 CUDA 等同于 DNN 自动使用 GPU。

## 摄像头 / 音频

Linux 下不导入 cv2-enumerate-cameras；`camera_sources.py` 使用 `/dev/video*` 和 V4L2。只运行一个摄像头服务。

```bash
python app.py --list-cameras
python audio_engine.py --list-devices
python audio_engine.py --device '实际输出设备名'
python app.py --camera 0 --backend v4l2 --width 640 --height 480
```

CSI 相机可使用显式管道（sensor-id、尺寸、格式须与实际传感器一致；**示例未在本设备验证**）：

```bash
python app.py --backend gstreamer --gstreamer \
  'nvarguscamerasrc sensor-id=0 ! video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1 ! nvvidconv ! video/x-raw,width=640,height=480,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! appsink drop=true max-buffers=1 sync=false'
```

音频后端为 sounddevice/PortAudio；按设备环境连接 ALSA/PulseAudio/USB 声卡，初始失败时 UI 必须显示 error。不要以 mock 的 played_events 宣称音箱发声。

远程观看推荐保持 loopback 并在电脑执行：

```bash
ssh -L 8765:127.0.0.1:8765 user@JETSON_IP
```

然后访问本机 `http://127.0.0.1:8765`。可信局域网可显式 `--host 0.0.0.0`，远端默认只读；需要远端录制/退出时再加 `--allow-remote-controls`。服务无认证，不在公网暴露。

## 必须补做的验收

先下载 README 指定照片，执行单元测试、`pip check`，再做 32 秒软件运行。之后按 TEST_REPORT 人工表记录设备型号、电源/功耗模式、分辨率、距离、倾角、光照和设备音频路由。采集至少 30 秒真人演奏和至少 60 秒静止，统计每种和弦、上下扫的实际动作数/触发/漏检/误触。

≥20 FPS 和 <200 ms 是验收目标，不是现有结论。报告处理 FPS、推理/ArUco p50/p95、事件到音频回调 p50/p95，并通过外部音视频或触发信号测量动作到实际声学输出；软件回调不能代替后者。未达标时先降低相机分辨率、检查设备缓存与声音缓冲、记录 CPU 频率/温度和 DNN 耗时，再评估 GPU 后端；不能修改测试阈值掩盖结果。
