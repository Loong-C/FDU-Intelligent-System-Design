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


class LegacyArucoBoardTracker:
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


# The strict zero-argument API above remains available to old Python clients.
# Service and new clients opt into learned corners or supply a BoardDefinition.
from dataclasses import dataclass
from board_definition import BoardDefinition


@dataclass(frozen=True)
class TrackingConfig:
    hold_s: float = .25
    ransac_px: float = 3.
    max_rmse_px: float = 2.
    min_inlier_ratio: float = .8
    min_coverage: float = .10
    min_spread_ratio: float = .035
    min_marker_edge_px: float = 8.
    min_hull_area_px: float = 400.
    max_normalized_condition: float = 1000.
    jump_diagonal: float = .18
    jump_diagonal_per_s: float = .8
    recovery_s: float = .10

    def __post_init__(self):
        if not all(np.isfinite(v) and (v >= 0 if k == 'hold_s' else v > 0) for k, v in vars(self).items()):
            raise ValueError('Tracking thresholds must be finite and positive')
        if self.min_inlier_ratio > 1 or self.min_coverage > 1 or self.min_spread_ratio > 1:
            raise ValueError('Tracking ratios must not exceed 1')


def _hull_area(points):
    return abs(cv.contourArea(cv.convexHull(np.float32(points))))


def _normalizer(points):
    center = np.mean(points, axis=0)
    scale = np.sqrt(2)/max(np.sqrt(np.mean(np.sum((points-center)**2, axis=1))), 1e-12)
    return np.array([[scale, 0, -scale*center[0]], [0, scale, -scale*center[1]], [0, 0, 1.]])


class ArucoBoardTracker:
    """Joint encoded-corner fit in raw pixels; quality is heuristic, never a probability."""
    def __init__(self, hold_s=.25, min_area_px=400., clock=monotonic_s, detector=None,
                 board=None, learn_legacy=False, config=None):
        self.config = config or TrackingConfig(hold_s=hold_s, min_hull_area_px=min_area_px)
        self.clock, self.board, self.learn_legacy = clock, board, learn_legacy
        self.legacy = LegacyArucoBoardTracker(self.config.hold_s, min_area_px, clock, detector)
        if detector is None and board is not None:
            parameters = cv.aruco.DetectorParameters()
            parameters.cornerRefinementMethod = cv.aruco.CORNER_REFINE_SUBPIX
            detector = cv.aruco.ArucoDetector(cv.aruco.getPredefinedDictionary(getattr(cv.aruco, board.dictionary)), parameters)
        self.detector = detector or self.legacy.detector
        self.reset()

    def reset(self):
        self.last_valid_H = self.last_valid_inverse = self.last_valid_mono_time = None
        self.last_time = None
        self.pending = None
        self.legacy.reset()

    def export_state(self):
        return dict(last_valid_H=None if self.last_valid_H is None else self.last_valid_H.tolist(),
                    last_valid_inverse=None if self.last_valid_inverse is None else self.last_valid_inverse.tolist(),
                    last_valid_mono_time=self.last_valid_mono_time, last_time=self.last_time,
                    pending=None if self.pending is None else [self.pending[0].tolist(), self.pending[1], self.pending[2]])

    def restore_state(self, state, time_offset=0.):
        """Seed only the beginning of a replay, including a recording begun during occlusion."""
        self.reset()
        for name in ('last_valid_H', 'last_valid_inverse'):
            value = state.get(name)
            if value is not None:
                value = np.asarray(value, dtype=float)
                if value.shape != (3, 3) or not np.isfinite(value).all():
                    raise ValueError('Invalid replay transform state')
                setattr(self, name, value)
        for name in ('last_valid_mono_time', 'last_time'):
            value = state.get(name)
            if value is not None:
                if not np.isfinite(value):
                    raise ValueError('Invalid replay clock state')
                setattr(self, name, value+time_offset)
        if state.get('pending') is not None:
            p, t, n = state['pending']
            self.pending = (np.asarray(p, dtype=float), t+time_offset, n)

    def _legacy_process(self, frame, now):
        result = self.legacy.process(frame, now)
        self.last_valid_H = self.legacy.last_valid_H
        self.last_valid_inverse = self.legacy.last_valid_inverse
        self.last_valid_mono_time = self.legacy.last_valid_mono_time
        if self.learn_legacy and result['status'] == 'valid':
            mapping = {m['id']: {'corners_uv': project(m['corners_px_raw'], self.last_valid_H).tolist()}
                       for m in result['markers'] if m['id'] in REQUIRED_IDS}
            try:
                self.board = BoardDefinition('legacy_learned', mapping, metadata={'method': 'legacy_center_bootstrap'})
            except ValueError:
                self.reset()
                result.update(status='lost', reason='invalid_legacy_corner_geometry',
                              homography_camera_to_instrument=None, homography_instrument_to_camera=None,
                              homography_age_s=None)
        result['tracking_mode'] = 'legacy_bootstrap' if self.learn_legacy else 'legacy_strict'
        result['board_id'] = 'legacy'
        result['pose_quality'] = dict(status=result['status'], reason=result['reason'],
                                     visible_marker_count=len(set(result['visible_ids']) & set(REQUIRED_IDS)),
                                     correspondence_count=4 if result['status'] == 'valid' else 0,
                                     inlier_count=4 if result['status'] == 'valid' else 0,
                                     inlier_ratio=1. if result['status'] == 'valid' else 0.,
                                     reprojection_rmse_px=None, coverage_ratio=None,
                                     age_s=result['homography_age_s'], method='legacy_center_bootstrap')
        return result

    def process(self, raw_frame, timestamp_monotonic_s=None):
        started = time.perf_counter()
        now = self.clock() if timestamp_monotonic_s is None else timestamp_monotonic_s
        if self.board is None:
            result = self._legacy_process(raw_frame, now)
            if self.board is None:
                return result
        c, board = self.config, self.board
        detected, ids, _ = self.detector.detectMarkers(raw_frame)
        counts = Counter(int(i) for i in (() if ids is None else ids.flatten()))
        markers, usable, invalid = [], {}, False
        for marker_id, corners in zip(() if ids is None else ids.flatten(), detected):
            marker_id = int(marker_id)
            try:
                p = np.asarray(corners, dtype=np.float64).reshape(4, 2)
            except (ValueError, TypeError):
                invalid |= marker_id in board.markers
                continue
            if not np.isfinite(p).all():
                invalid |= marker_id in board.markers
                continue
            markers.append(dict(id=marker_id, corners_px_raw=p.tolist(), center_px_raw=p.mean(axis=0).tolist()))
            if marker_id not in board.markers:
                continue
            edge = np.linalg.norm(np.roll(p, -1, axis=0)-p, axis=1)
            if not cv.isContourConvex(np.float32(p)) or cv.contourArea(np.float32(p), oriented=True) <= 1:
                invalid = True
            elif edge.min() >= c.min_marker_edge_px:
                usable[marker_id] = p
        visible = sorted(set(counts) & set(board.markers))
        q = dict(status='lost', visible_marker_count=len(visible), correspondence_count=0,
                 inlier_count=0, inlier_ratio=0., ransac_inlier_count=0, inlier_marker_count=0, reprojection_rmse_px=None,
                 coverage_ratio=0., spread_ratio=0., normalized_condition=None, age_s=None, reason=None)
        H = inverse = None
        reason = 'missing_or_too_small_markers'
        hard_failure = None
        if not np.isfinite(now) or (self.last_time is not None and now <= self.last_time):
            hard_failure = 'invalid_timestamp'
        elif any(counts[i] > 1 for i in visible):
            hard_failure = 'duplicate_registered_ids'
        elif invalid:
            hard_failure = 'invalid_marker_coordinates'
        if hard_failure:
            self.reset()
            reason = hard_failure
        else:
            self.last_time = now
            if usable:
                keys = sorted(usable)
                uv = np.concatenate([board.markers[k]['corners_uv'] for k in keys]).astype(np.float64)
                px = np.concatenate([usable[k] for k in keys])
                q['correspondence_count'] = len(uv)
                try:
                    # Fit UV -> pixels so RANSAC threshold and residuals are in pixels.
                    inverse, mask = cv.findHomography(uv, px, cv.RANSAC, c.ransac_px, maxIters=2000, confidence=.995)
                    if inverse is None or mask is None:
                        raise ValueError('homography_fit_failed')
                    mask = mask.ravel().astype(bool)
                    q['ransac_inlier_count'] = int(mask.sum())
                    # Reject partially supported markers as units; do not fit a board from accidental corners.
                    complete = mask.reshape(-1, 4).all(axis=1)
                    mask = np.repeat(complete, 4)
                    q.update(inlier_count=int(mask.sum()), inlier_ratio=float(mask.mean()),
                             inlier_marker_count=int(complete.sum()))
                    if mask.sum() < 4:
                        raise ValueError('inconsistent_marker_correspondences')
                    inverse, _ = cv.findHomography(uv[mask], px[mask], 0)
                    H = np.linalg.inv(inverse)
                    predicted = project(uv[mask], inverse)
                    if predicted is None:
                        raise ValueError('invalid_homography')
                    rmse = float(np.sqrt(np.mean(np.sum((predicted-px[mask])**2, axis=1))))
                    normalized = _normalizer(px[mask]) @ inverse @ np.linalg.inv(_normalizer(uv[mask]))
                    condition = float(np.linalg.cond(normalized))
                    support = np.vstack([board.points, BOARD_UV, board.outline_uv or []]) if board.outline_uv else np.vstack([board.points, BOARD_UV])
                    denominator = np.column_stack([support, np.ones(len(support))]) @ inverse[2]
                    plane = project(BOARD_UV[list(PERIMETER)], inverse)
                    if (not np.isfinite(condition) or condition > c.max_normalized_condition or
                            np.min(denominator)*np.max(denominator) <= 0 or plane is None or
                            not cv.isContourConvex(np.float32(plane)) or
                            _hull_area(plane) < c.min_hull_area_px or
                            np.max(np.abs(plane)) > max(raw_frame.shape[:2])*100):
                        raise ValueError('unstable_or_extreme_perspective')
                    eig = np.linalg.eigvalsh(np.cov(uv[mask].T))
                    spread = float(np.sqrt(max(0, eig[0])/max(eig[-1], 1e-12)))
                    coverage = min(1., _hull_area(uv[mask])/max(_hull_area(support), 1e-12))
                    q.update(reprojection_rmse_px=rmse, coverage_ratio=coverage, spread_ratio=spread,
                             normalized_condition=condition)
                    reason = None
                    if q['inlier_marker_count'] < 2:
                        reason = 'single_marker_extrapolation'
                    elif q['inlier_ratio'] < c.min_inlier_ratio or rmse > c.max_rmse_px:
                        reason = 'inconsistent_correspondences_or_reprojection'
                    elif coverage < c.min_coverage or spread < c.min_spread_ratio or _hull_area(px[mask]) < c.min_hull_area_px:
                        reason = 'insufficient_spatial_coverage'
                    if reason is None and self.last_valid_inverse is not None:
                        old = project(BOARD_UV, self.last_valid_inverse)
                        current = project(BOARD_UV, inverse)
                        dt = now-self.last_valid_mono_time
                        jump = np.max(np.linalg.norm(current-old, axis=1))/np.hypot(*raw_frame.shape[:2])
                        q['temporal_jump_diagonal'] = float(jump)
                        if self.pending is not None or jump > c.jump_diagonal+c.jump_diagonal_per_s*min(dt, c.hold_s):
                            reason = 'implausible_transform_jump'
                            if self.pending is None or np.max(np.linalg.norm(current-self.pending[0], axis=1)) > .04*np.hypot(*raw_frame.shape[:2]):
                                self.pending = (current, now, 1)
                            else:
                                self.pending = (self.pending[0], self.pending[1], self.pending[2]+1)
                                if now-self.pending[1] >= c.recovery_s and self.pending[2] >= 3:
                                    reason = None
                    if reason is None:
                        self.last_valid_H, self.last_valid_inverse, self.last_valid_mono_time = H, inverse, now
                        self.pending = None
                        q['status'] = 'valid'
                    else:
                        q['status'] = 'degraded'
                        if reason != 'implausible_transform_jump':
                            self.pending = None
                    q['age_s'] = 0.
                except (cv.error, ValueError, np.linalg.LinAlgError) as exc:
                    H = inverse = None
                    reason = str(exc) if isinstance(exc, ValueError) else 'invalid_homography'
            if H is None and self.last_valid_mono_time is not None:
                age = now-self.last_valid_mono_time
                q['age_s'] = age
                if age <= c.hold_s:
                    q['status'] = 'held'
                    H, inverse = self.last_valid_H, self.last_valid_inverse
                else:
                    self.last_valid_H = self.last_valid_inverse = self.last_valid_mono_time = None
                    self.pending = None
                    reason = 'hold_expired: '+reason
        q['reason'] = reason
        return dict(status=q['status'], reason=reason, dictionary=board.dictionary, board_id=board.board_id,
                    tracking_mode='registered_corners', required_ids=sorted(board.markers), visible_ids=sorted(counts),
                    markers=markers, outline_uv=board.outline_uv, pose_quality=q,
                    homography_camera_to_instrument=None if H is None else H.tolist(),
                    homography_instrument_to_camera=None if inverse is None else inverse.tolist(),
                    homography_age_s=q['age_s'], source_timestamp_monotonic_s=float(now) if np.isfinite(now) else None,
                    aruco_ms=round((time.perf_counter()-started)*1000, 3))
