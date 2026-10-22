"""Single-frame orchestration; camera ownership stays in app.Service."""
import time
from collections import deque
import cv2 as cv
import numpy as np
from aruco_tracking import ArucoBoardTracker
from hand_tracking import HandTracker, annotate
from instrument_geometry import InstrumentLayout, fuse_hands, overlay_polygons, raw_to_display_xy
from instrument_logic import InstrumentLogic
from timing import monotonic_s


class PerceptionPipeline:
    def __init__(self, hands=None, board=None, layout=None, logic=None, audio=None):
        self.hands = hands if hands is not None else HandTracker()
        self.board = board if board is not None else ArucoBoardTracker()
        self.layout = layout or InstrumentLayout()
        self.logic = logic if logic is not None else InstrumentLogic(self.layout)
        self.audio = audio
        self.recent_events = deque(maxlen=32)

    def process(self, raw_frame, timestamp_unix_s=None, timestamp_monotonic_s=None):
        captured = time.time() if timestamp_unix_s is None else timestamp_unix_s
        mono = monotonic_s() if timestamp_monotonic_s is None else timestamp_monotonic_s
        started = time.perf_counter()
        display, packet = self.hands.process(raw_frame, captured)
        instrument = self.board.process(raw_frame, mono)
        instrument['source_frame_id'] = packet['frame_id']
        fuse_hands(packet, instrument)
        packet.update(timestamp_monotonic_s=mono, status='running', layout=self.layout.regions(),
                      vision_total_ms=round((time.perf_counter() - started) * 1000, 3))
        packet['interaction'], packet['events'] = self.logic.process(packet)
        for event in packet['events']:
            self.recent_events.append(event)
            if self.audio is not None:
                self.audio.submit(event)
        packet['recent_events'] = list(self.recent_events)
        packet['audio'] = self.audio.snapshot() if self.audio is not None else {'status': 'disabled'}
        packet['audio_status'] = packet['audio']['status']
        return display, packet


def annotate_instrument(display, packet, layout):
    canvas = annotate(display, packet)
    board = packet['instrument']
    state = packet.get('interaction', {})
    green, amber, muted = (176, 214, 88), (78, 174, 243), (130, 130, 130)

    def integer_points(points):
        # Projective points close to a horizon can be huge; protect OpenCV int32 conversion.
        return np.rint(np.clip(points, -1e6, 1e6)).astype(np.int32)

    for marker in board['markers']:
        points = raw_to_display_xy(marker['corners_px_raw'], packet['frame_width'], packet['mirrored'])
        points = integer_points(points)
        cv.polylines(canvas, [points], True, green, 1, cv.LINE_AA)
        cv.putText(canvas, str(marker['id']), tuple(points[0]), cv.FONT_HERSHEY_SIMPLEX, .5, amber, 2)
    for name, points in overlay_polygons(packet, layout).items():
        if points is None:
            continue
        polygon = integer_points(points)
        active = name == state.get('current_chord') and state.get('chord_valid')
        color = muted if board['status'] != 'valid' else amber if active or name in ('strum', 'axis') else green
        cv.polylines(canvas, [polygon], name != 'axis', color, 2, cv.LINE_AA)
        if name in ('C', 'G', 'Am', 'F'):
            cv.putText(canvas, name, tuple(integer_points(np.mean(points, axis=0))),
                       cv.FONT_HERSHEY_SIMPLEX, .6, color, 2, cv.LINE_AA)
    label = f"Board: {board['status']} | chord: {state.get('current_chord') or '-'}"
    cv.putText(canvas, label, (12, 24), cv.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2, cv.LINE_AA)
    if packet.get('source') == 'synthetic':
        cv.putText(canvas, 'SIMULATION / scripted hands', (15, canvas.shape[0]-12),
                   cv.FONT_HERSHEY_SIMPLEX, .45, (180, 220, 200), 1, cv.LINE_AA)
    return canvas
