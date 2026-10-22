"""Explicit simulation for repeatable no-camera demos; never claims model inference.

Real ArUco detection processes the generated marker image. Only hand landmarks
are scripted, using the known synthetic board coordinates rather than a detector.
"""
import cv2 as cv
import numpy as np
from hand_tracking import NAMES, EDGES
from instrument_geometry import raw_to_display_xy, InstrumentLayout


def board_image():
    image = np.full((480, 640, 3), (35, 45, 39), np.uint8)
    cv.rectangle(image, (45, 45), (595, 435), (222, 226, 214), -1)
    dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_4X4_50)
    for i, (x, y) in enumerate(((60, 60), (520, 60), (60, 360), (520, 360))):
        marker = cv.aruco.generateImageMarker(dictionary, i, 60)
        image[y:y+60, x:x+60] = cv.cvtColor(marker, cv.COLOR_GRAY2BGR)
    return image


class SyntheticHandTracker:
    def __init__(self, mirror=True, layout=None):
        self.mirror, self.layout = mirror, layout or InstrumentLayout()
        self.frame_id = 0
        self.started = None

    def process(self, raw_frame, timestamp):
        self.started = timestamp if self.started is None else self.started
        elapsed = timestamp - self.started
        self.frame_id += 1
        index = int(elapsed/3) % 4
        phase = elapsed % 1.2
        v = (.3 if phase < .3 else .3+(phase-.3)*2 if phase < .5 else
             .7 if phase < .9 else .7-(phase-.9)*2 if phase < 1.1 else .3)
        hands = []
        for role, u, y, tid in (('Left', .11+index*.14, .5, 1), ('Right', .78, v, 2)):
            # Small visible hand skeleton; keep MCP mean and index tip at the scripted target.
            offsets = np.array([[0., .10]] + [[(finger-2)*.025, .07-joint*.025]
                               for finger in range(5) for joint in range(4)])
            reference = offsets[[5, 9, 13, 17]].mean(axis=0) if role == 'Left' else offsets[8]
            uv = offsets - reference + [u, y]
            if self.layout.flip_u:
                uv[:, 0] = 1 - uv[:, 0]
            raw = uv * [460., 300.] + [89.5, 89.5]
            display = raw_to_display_xy(raw, raw_frame.shape[1], self.mirror)
            screen = np.column_stack((display, np.zeros(21)))
            hands.append({'handedness': role, 'handedness_score': 1., 'confidence': 1., 'palm_confidence': 1.,
                          'track_id': tid, 'bbox_px': [*display.min(axis=0), *display.max(axis=0)],
                          'landmarks_px': screen.tolist(),
                          'landmarks_normalized': (screen/[raw_frame.shape[1], raw_frame.shape[0], raw_frame.shape[1]]).tolist(),
                          'landmarks_world_m': np.zeros((21, 3)).tolist()})
        return (cv.flip(raw_frame, 1) if self.mirror else raw_frame.copy()), {
            'schema_version': 1, 'frame_id': self.frame_id, 'timestamp_unix_s': timestamp,
            'frame_width': raw_frame.shape[1], 'frame_height': raw_frame.shape[0],
            'mirrored': self.mirror, 'inference_ms': 0., 'landmark_names': NAMES,
            'connections': EDGES, 'hands': hands, 'source': 'synthetic',
            'simulation_notice': 'Scripted hands; generated marker image. Not live camera or model inference.'}
