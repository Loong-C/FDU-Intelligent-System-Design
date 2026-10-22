"""Single-camera MotionMuse service, HTTP dashboard and asynchronous recording."""
import argparse
import base64
import ipaddress
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import cv2 as cv
from hand_tracking import ROOT, HandTracker
from pipeline import PerceptionPipeline, annotate_instrument
from instrument_geometry import InstrumentLayout
from instrument_logic import InstrumentLogic, InteractionConfig
from audio_engine import AudioEngine, MockAudioBackend, SoundDeviceBackend
from camera_sources import cameras, open_camera
from recording import Recorder
from timing import monotonic_s

LOG = logging.getLogger('motionmuse')


class Service:
    def __init__(self, args):
        self.args = args
        self.lock = threading.RLock()
        self.record_control = threading.Lock()
        self.stop = threading.Event()
        self.packet = {'schema_version': 2, 'hands': [], 'status': 'starting',
                       'instrument': {'status': 'lost', 'reason': 'starting', 'visible_ids': []},
                       'interaction': {'current_chord': None, 'chord_valid': False},
                       'events': [], 'recent_events': [], 'audio_status': 'starting'}
        self.jpeg = None
        self.backend_name = None
        self.recording = self.last_recording = self.recording_error = None
        self.audio = self.pipeline = None
        self.device_list = [] if args.demo or args.video else cameras()
        selected = next((c for c in self.device_list if 'c270' in c['name'].lower()), None)
        selected = selected or next((c for c in self.device_list if 'ir camera' not in c['name'].lower()), None)
        self.index = args.camera if args.camera is not None else (selected['index'] if selected else 0)
        self.camera_name = ('Synthetic demo' if args.demo else str(args.video) if args.video else
                            next((c['name'] for c in self.device_list if c['index'] == self.index), str(self.index)))
        self.worker = threading.Thread(target=self.run, name='single-camera-worker', daemon=True)

    def set_recording(self, enabled):
        # Serialize control requests, but drain files outside the snapshot/camera lock.
        with self.record_control:
            with self.lock:
                old = None
                if enabled and self.recording is None:
                    self.recording = Recorder(ROOT / 'outputs')
                    self.last_recording = str(self.recording.folder)
                    self.recording_error = None
                elif not enabled and self.recording is not None:
                    old, self.recording = self.recording, None
            if old is not None:
                old.close()
                with self.lock:
                    self.recording_error = old.error

    def latest(self):
        with self.lock:
            result = dict(self.packet, recording=self.recording is not None and not self.recording.stop.is_set(),
                          recording_error=self.recording.error if self.recording else self.recording_error,
                          last_recording=self.last_recording, camera_name=self.camera_name,
                          camera_index=self.index, camera_backend=self.backend_name, available_cameras=self.device_list)
            if self.audio is not None:
                result['audio'] = self.audio.snapshot()
                result['audio_status'] = result['audio']['status']
            return result

    def snapshot(self):
        with self.lock:
            return self.latest(), self.jpeg

    def publish(self, display, packet):
        ok, encoded = cv.imencode('.jpg', display, [cv.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError('JPEG encoding failed')
        # Strict serialization guards recorded and HTTP data alike.
        json.dumps(packet, allow_nan=False)
        with self.lock:
            self.packet, self.jpeg = packet, encoded.tobytes()
            if self.recording is not None:
                self.recording.submit(packet)

    def fail_frame(self, message):
        with self.lock:
            self.packet = dict(self.packet, status='error', error=message, hands=[], events=[],
                               instrument={'status': 'lost', 'reason': 'camera_unavailable', 'visible_ids': [],
                                           'markers': [], 'homography_camera_to_instrument': None,
                                           'homography_instrument_to_camera': None, 'homography_age_s': None},
                               interaction=self.pipeline.logic.invalidate() if self.pipeline else
                               {'current_chord': None, 'chord_valid': False})
            self.jpeg = None
        if self.pipeline is not None:
            self.pipeline.board.reset()

    def run(self):
        cap = None
        try:
            cv.setNumThreads(4)
            layout = InstrumentLayout(flip_u=self.args.layout == 'flip-u')
            config = InteractionConfig()
            if self.args.interaction_config:
                with open(self.args.interaction_config, encoding='utf-8') as file:
                    config = InteractionConfig(**json.load(file))
            if self.args.demo:
                from synthetic_input import SyntheticHandTracker, board_image
                tracker = SyntheticHandTracker(mirror=not self.args.no_mirror, layout=layout)
                frame = board_image()
                self.backend_name = 'synthetic'
            else:
                tracker = HandTracker(self.args.palm_threshold, self.args.hand_threshold, mirror=not self.args.no_mirror)
                cap, frame = open_camera(self.index, self.camera_name, self.args.backend,
                                         self.args.width, self.args.height, self.args.gstreamer, self.args.video)
                self.backend_name = cap.getBackendName()
            audio_mode = self.args.audio or ('mock' if self.args.demo else 'sounddevice')
            device = self.args.audio_device
            device = int(device) if device and device.isdigit() else device
            backend = MockAudioBackend() if audio_mode in ('mock', 'off') else SoundDeviceBackend(device)
            self.audio = AudioEngine(backend, enabled=audio_mode != 'off')
            self.pipeline = PerceptionPipeline(hands=tracker, layout=layout, audio=self.audio,
                                               logic=InstrumentLogic(layout, config))
            previous, fps, failed = time.perf_counter(), 0., 0
            deadline = time.monotonic() + self.args.duration if self.args.duration else None
            first = True
            while not self.stop.is_set() and (deadline is None or time.monotonic() < deadline):
                if not self.args.demo and not first:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        if self.args.video:
                            break
                        failed += 1
                        self.fail_frame('Camera frame unavailable')
                        if failed >= 30:
                            raise RuntimeError('Camera disconnected; restart after reconnecting.')
                        self.stop.wait(.1)
                        continue
                first, failed = False, 0
                captured, mono = time.time(), monotonic_s()
                display, packet = self.pipeline.process(frame, captured, mono)
                packet.setdefault('source', 'video' if self.args.video else 'camera')
                if audio_mode == 'mock' and self.audio.status == 'mock':
                    backend.pump()
                    packet['audio'] = self.audio.snapshot()
                    packet['audio_status'] = packet['audio']['status']
                now = time.perf_counter()
                instant = 1/max(now-previous, .0001)
                fps = instant if not fps else .9*fps + .1*instant
                previous = now
                packet.update(fps=round(fps, 1))
                self.publish(annotate_instrument(display, packet, layout), packet)
                if self.args.demo:
                    self.stop.wait(1/30)
            with self.lock:
                self.packet = dict(self.packet, status='stopped', hands=[], events=[],
                                   interaction=self.pipeline.logic.invalidate('service_stopped'))
                self.jpeg = None
        except Exception as exc:
            LOG.exception('Camera worker failed')
            self.fail_frame(str(exc))
        finally:
            if cap is not None:
                cap.release()
            if self.audio is not None:
                self.audio.close()
            self.set_recording(False)


def handler_for(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, content, content_type, headers=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for name, value in (headers or {}).items():
                self.send_header(name, str(value))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path in ('/', '/app.js', '/style.css'):
                    filename = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
                    content_type = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8',
                                    '/style.css': 'text/css; charset=utf-8'}[path]
                    self.send(200, (ROOT/'web'/filename).read_bytes(), content_type)
                elif path in ('/api/landmarks', '/api/state'):
                    self.send(200, json.dumps(service.latest(), allow_nan=False).encode(), 'application/json')
                elif path == '/api/snapshot':
                    packet, jpeg = service.snapshot()
                    body = {'packet': packet, 'image_base64': base64.b64encode(jpeg).decode() if jpeg else None}
                    self.send(200, json.dumps(body, allow_nan=False).encode(), 'application/json')
                elif path == '/frame.jpg':
                    packet, jpeg = service.snapshot()
                    self.send(200 if jpeg else 503, jpeg or b'Camera not ready',
                              'image/jpeg' if jpeg else 'text/plain', {'X-Frame-Id': packet.get('frame_id', 0)})
                elif path == '/favicon.ico':
                    self.send(204, b'', 'image/x-icon')
                else:
                    self.send(404, b'Not found', 'text/plain')
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            origin = self.headers.get('Origin')
            if ((origin and origin != f'http://{self.headers.get("Host")}') or
                    self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                self.send(403, b'Cross-origin request rejected', 'text/plain')
                return
            if not ipaddress.ip_address(self.client_address[0]).is_loopback and not service.args.allow_remote_controls:
                self.send(403, b'Remote controls disabled; use SSH forwarding or --allow-remote-controls on a trusted LAN', 'text/plain')
                return
            path = urlparse(self.path).path
            try:
                if path == '/api/record/start':
                    if service.latest()['status'] != 'running':
                        self.send(409, b'Camera not running', 'text/plain')
                        return
                    service.set_recording(True)
                elif path == '/api/record/stop':
                    service.set_recording(False)
                elif path == '/api/shutdown':
                    service.stop.set()
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self.send(404, b'Not found', 'text/plain')
                    return
                self.send(200, json.dumps(service.latest(), allow_nan=False).encode(), 'application/json')
            except (OSError, RuntimeError) as exc:
                self.send(500, str(exc).encode(), 'text/plain; charset=utf-8')
    return Handler


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', type=int, help='Camera index; default prefers Logitech C270')
    parser.add_argument('--list-cameras', action='store_true')
    parser.add_argument('--backend', choices=['auto', 'dshow', 'msmf', 'v4l2', 'gstreamer'], default='auto')
    parser.add_argument('--gstreamer', help='Explicit GStreamer pipeline ending in appsink')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--demo', action='store_true', help='Scripted hands + generated ArUco, clearly labeled simulation')
    source.add_argument('--video', help='Process a local video through the real ONNX detector')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1', help='Explicit bind address; remote video has no authentication')
    parser.add_argument('--allow-remote-controls', action='store_true', help='Enable record/shutdown for trusted LAN clients')
    parser.add_argument('--no-mirror', action='store_true')
    parser.add_argument('--layout', choices=['standard', 'flip-u'], default='standard')
    parser.add_argument('--interaction-config', help='JSON overrides for InteractionConfig thresholds')
    parser.add_argument('--audio', choices=['sounddevice', 'mock', 'off'], help='Default sounddevice; demo defaults to mock')
    parser.add_argument('--audio-device', help='Output device index or PortAudio device name')
    parser.add_argument('--duration', type=float, help='Optional bounded processing duration in seconds')
    parser.add_argument('--palm-threshold', type=float, default=.6)
    parser.add_argument('--hand-threshold', type=float, default=.8)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.list_cameras:
        print(json.dumps(cameras(), ensure_ascii=False, indent=2))
        return
    if (args.width < 1 or args.height < 1 or not 0 < args.palm_threshold <= 1 or
            not 0 < args.hand_threshold <= 1 or (args.duration is not None and args.duration <= 0)):
        parser.error('Dimensions/duration must be positive; thresholds must be in (0, 1].')
    if args.backend == 'gstreamer' and not args.gstreamer:
        parser.error('--backend gstreamer requires --gstreamer')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    service = Service(args)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(service))
    service.worker.start()
    if args.host not in ('127.0.0.1', 'localhost'):
        LOG.warning('Remote viewing enabled without authentication. Use a trusted LAN or SSH tunnel, not the public Internet.')
    LOG.info('Dashboard: http://%s:%s', args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.stop.set()
        service.worker.join(timeout=10)
        service.set_recording(False)
        server.server_close()


if __name__ == '__main__':
    main()
