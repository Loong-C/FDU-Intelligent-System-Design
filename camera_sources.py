"""Platform camera adapters. Importing on Linux never imports Windows enumeration."""
import sys
from pathlib import Path
import cv2 as cv


def cameras(backend=None):
    if sys.platform == 'win32':
        from cv2_enumerate_cameras import enumerate_cameras
        backend = cv.CAP_DSHOW if backend is None else backend
        return [{'index': c.index, 'name': c.name, 'backend': c.backend} for c in enumerate_cameras(backend)]
    return [{'index': int(p.name[5:]), 'name': str(p), 'backend': cv.CAP_V4L2}
            for p in sorted(Path('/dev').glob('video[0-9]*')) if p.name[5:].isdigit()]


def open_camera(index, name, backend='auto', width=640, height=480, gstreamer=None, video=None):
    if video:
        choices = [(str(video), cv.CAP_ANY)]
    elif backend == 'gstreamer':
        if not gstreamer:
            raise ValueError('--gstreamer pipeline is required')
        choices = [(gstreamer, cv.CAP_GSTREAMER)]
    else:
        backends = {'auto': [cv.CAP_DSHOW, cv.CAP_MSMF] if sys.platform == 'win32' else [cv.CAP_V4L2],
                    'dshow': [cv.CAP_DSHOW], 'msmf': [cv.CAP_MSMF], 'v4l2': [cv.CAP_V4L2]}
        choices = []
        for api in backends[backend]:
            device = next((d for d in cameras(api) if d['name'] == name), None)
            choices.append((device['index'] if device else index, api))
    for source, api in choices:
        cap = cv.VideoCapture(source, api)
        if cap.isOpened():
            if not video:
                cap.set(cv.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv.CAP_PROP_FPS, 30)
                cap.set(cv.CAP_PROP_BUFFERSIZE, 1)  # Best effort; support depends on driver.
            ok, first = cap.read()
            if ok and first is not None:
                return cap, first
        cap.release()  # Release before trying the next backend.
    raise RuntimeError(f'Cannot open camera/source {name}; check connection, backend and device ownership.')
