"""ArUco board localization adapted from SMF-an/MotionMuse at 2426ce1.

Original ID ordering, quad validation and explicit hold state are retained.
See docs/integration/BASELINE.md for attribution and redistribution limitations.
"""
from collections import Counter
import time
import cv2 as cv
import numpy as np
from instrument_geometry import BOARD_UV, PERIMETER, project
from timing import monotonic_s

REQUIRED_IDS = (0, 1, 2, 3)


def _valid_quad(points, min_area_px):
    polygon = points[list(PERIMETER)].astype(np.float32)
    if not np.isfinite(polygon).all() or not cv.isContourConvex(polygon):
        return False
    if abs(cv.contourArea(polygon)) < min_area_px:
        return False
    edges = np.roll(polygon, -1, axis=0) - polygon
    following = np.roll(edges, -1, axis=0)
    cross = edges[:, 0] * following[:, 1] - edges[:, 1] * following[:, 0]
    lengths = np.linalg.norm(edges, axis=1) * np.linalg.norm(following, axis=1)
    return bool(np.all(lengths > 0) and np.min(np.abs(cross) / lengths) >= .01)


class ArucoBoardTracker:
    def __init__(self, hold_s=.25, min_area_px=400., clock=monotonic_s, detector=None):
        if hold_s < 0 or min_area_px <= 0:
            raise ValueError('Invalid board tracking thresholds')
        if detector is None:
            if not hasattr(cv, 'aruco') or not hasattr(cv.aruco, 'ArucoDetector'):
                raise RuntimeError('OpenCV with cv2.aruco.ArucoDetector (>=4.7) is required; see JETSON.md')
            dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_4X4_50)
            parameters = cv.aruco.DetectorParameters()
            parameters.cornerRefinementMethod = cv.aruco.CORNER_REFINE_SUBPIX
            detector = cv.aruco.ArucoDetector(dictionary, parameters)
        self.detector, self.clock = detector, clock
        self.hold_s, self.min_area_px = hold_s, min_area_px
        self.reset()

    def reset(self):
        self.last_valid_H = self.last_valid_inverse = self.last_valid_mono_time = None

    def process(self, raw_frame, timestamp_monotonic_s=None):
        started = time.perf_counter()
        now = self.clock() if timestamp_monotonic_s is None else timestamp_monotonic_s
        detected, ids, _ = self.detector.detectMarkers(raw_frame)
        counts, centers, markers = Counter(), {}, []
        invalid = False
        for marker_id, corners in zip(() if ids is None else ids.flatten(), detected):
            marker_id = int(marker_id)
            counts[marker_id] += 1
            points = np.asarray(corners, dtype=np.float32).reshape(4, 2)
            if not np.isfinite(points).all():
                invalid = invalid or marker_id in REQUIRED_IDS
                continue
            center = points.mean(axis=0)
            centers[marker_id] = center
            markers.append({'id': marker_id, 'corners_px_raw': points.tolist(), 'center_px_raw': center.tolist()})
        status, reason, age = 'lost', 'missing_markers', None
        if not np.isfinite(now) or (self.last_valid_mono_time is not None and now < self.last_valid_mono_time):
            reason = 'invalid_timestamp'
            self.reset()
        elif invalid or any(counts[i] > 1 for i in REQUIRED_IDS):
            reason = 'invalid_marker_coordinates' if invalid else 'duplicate_required_ids'
            self.reset()
        elif all(counts[i] == 1 for i in REQUIRED_IDS):
            ordered = np.float32([centers[i] for i in REQUIRED_IDS])
            self.reset()
            reason = 'invalid_marker_layout'
            if _valid_quad(ordered, self.min_area_px):
                reason = 'invalid_homography'
                matrix = cv.getPerspectiveTransform(ordered, BOARD_UV)
                try:
                    inverse = np.linalg.inv(matrix)
                    forward, backward = project(ordered, matrix), project(BOARD_UV, inverse)
                    if (forward is not None and backward is not None and
                            np.allclose(forward, BOARD_UV, atol=1e-5) and
                            np.allclose(backward, ordered, atol=.05)):
                        self.last_valid_H, self.last_valid_inverse = matrix, inverse
                        self.last_valid_mono_time = now
                        status, reason, age = 'valid', None, 0.0
                except np.linalg.LinAlgError:
                    pass
        elif self.last_valid_mono_time is not None:
            age = now - self.last_valid_mono_time
            if age <= self.hold_s:
                status, reason = 'held', 'temporary_marker_occlusion'
            else:
                reason = 'hold_expired'
                self.reset()
        return {'status': status, 'reason': reason, 'dictionary': 'DICT_4X4_50',
                'required_ids': list(REQUIRED_IDS), 'visible_ids': sorted(counts), 'markers': markers,
                'homography_camera_to_instrument': None if self.last_valid_H is None else self.last_valid_H.tolist(),
                'homography_instrument_to_camera': None if self.last_valid_inverse is None else self.last_valid_inverse.tolist(),
                'homography_age_s': age, 'source_timestamp_monotonic_s': float(now) if np.isfinite(now) else None,
                'aruco_ms': round((time.perf_counter() - started) * 1000, 3)}
