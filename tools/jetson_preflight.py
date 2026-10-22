"""Read-only environment probe; does not flash, install or change Jetson settings."""
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def command(args):
    if not shutil.which(args[0]):
        return {'status': 'unavailable'}
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return {'returncode': result.returncode, 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}
    except Exception as exc:
        return {'error': str(exc)}


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    report = {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
              'python_minimum_ok': sys.version_info >= (3, 10), 'hardware_acceptance': 'NOT TESTED'}
    for name, path in [('l4t', '/etc/nv_tegra_release'), ('os_release', '/etc/os-release'),
                       ('device_model', '/proc/device-tree/model')]:
        p = Path(path)
        report[name] = p.read_text(errors='replace').replace('\x00', '') if p.exists() else None
    for name, args in [('cuda', ['nvcc', '--version']), ('packages', ['dpkg-query', '-W', 'nvidia-jetpack', 'nvidia-l4t-core', 'libnvinfer8']),
                       ('v4l2', ['v4l2-ctl', '--list-devices']), ('alsa', ['aplay', '-l'])]:
        report[name] = command(args)
    try:
        import cv2 as cv
        import numpy as np
        report['opencv'] = {'version': cv.__version__, 'aruco_detector': hasattr(getattr(cv, 'aruco', None), 'ArucoDetector'),
                            'cuda_devices': cv.cuda.getCudaEnabledDeviceCount(), 'build': cv.getBuildInformation()}
        if sys.version_info >= (3, 10):
            from hand_tracking import HandTracker
            tracker = HandTracker()
            _, packet = tracker.process(np.zeros((480, 640, 3), np.uint8))
            report['onnx_blank_inference'] = {'status': 'PASS', 'inference_ms': packet['inference_ms'], 'hands': len(packet['hands'])}
    except Exception as exc:
        report['vision_error'] = str(exc)
    try:
        import sounddevice as sd
        report['audio_devices'] = list(sd.query_devices())
    except Exception as exc:
        report['audio_error'] = str(exc)
    output = root/'outputs/jetson_preflight.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(output)
    print('Environment inventory only. Camera capture, playback, target FPS and acoustic latency require separate acceptance.')


if __name__ == '__main__':
    main()
