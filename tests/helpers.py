import cv2 as cv
import numpy as np
from hand_tracking import NAMES, EDGES


def marker_image():
    image = np.full((480, 640, 3), 255, np.uint8)
    dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_4X4_50)
    for i, (x, y) in enumerate(((60, 60), (520, 60), (60, 360), (520, 360))):
        marker = cv.aruco.generateImageMarker(dictionary, i, 60)
        image[y:y+60, x:x+60] = cv.cvtColor(marker, cv.COLOR_GRAY2BGR)
    return image


def hand(role, point, track_id):
    return {'handedness': role, 'handedness_score': .99, 'confidence': .99,
            'track_id': track_id, 'landmarks_instrument_uv': [list(point) for _ in range(21)],
            'landmarks_px': [[point[0]*640, point[1]*480, 0.] for _ in range(21)],
            'landmarks_normalized': [[*point, 0.] for _ in range(21)],
            'landmarks_world_m': [[0., 0., 0.] for _ in range(21)]}


def packet(t, right=(.78, .3), left=(.1, .5), frame_id=None, board='valid'):
    hands = []
    if left is not None:
        hands.append(hand('Left', left, 1))
    if right is not None:
        hands.append(hand('Right', right, 2))
    return {'schema_version': 2, 'status': 'running', 'frame_id': int(t*1000)+1 if frame_id is None else frame_id,
            'timestamp_unix_s': 1792666800+t, 'timestamp_monotonic_s': t,
            'frame_width': 640, 'frame_height': 480, 'mirrored': False,
            'inference_ms': 0., 'hands': hands, 'landmark_names': NAMES, 'connections': EDGES,
            'instrument': {'status': board}}
