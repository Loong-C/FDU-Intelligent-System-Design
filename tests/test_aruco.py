import json
import unittest
from unittest.mock import Mock
import cv2 as cv
import numpy as np
from aruco_tracking import ArucoBoardTracker
from instrument_geometry import BOARD_UV, project
from tests.helpers import marker_image


class ArucoTests(unittest.TestCase):
    def test_synthetic_and_perspective(self):
        base = marker_image()
        source = np.float32([[0, 0], [639, 0], [0, 479], [639, 479]])
        for target in (source, np.float32([[70, 30], [600, 50], [20, 450], [570, 420]]),
                       np.float32([[120, 90], [540, 10], [50, 390], [610, 460]])):
            warp = cv.getPerspectiveTransform(source, target)
            image = cv.warpPerspective(base, warp, (640, 480), borderValue=(255, 255, 255))
            result = ArucoBoardTracker().process(image, 10.)
            self.assertEqual(result['status'], 'valid')
            centers = {m['id']: m['center_px_raw'] for m in result['markers']}
            np.testing.assert_allclose(project([centers[i] for i in range(4)], result['homography_camera_to_instrument']), BOARD_UV, atol=1e-5)
            # Independently transformed interior point remains close despite raster corner refinement.
            raw = project([[320., 240.]], warp)
            uv = project(raw, result['homography_camera_to_instrument'])
            np.testing.assert_allclose(uv, [[(320-89.5)/460, (240-89.5)/300]], atol=.008)
            json.dumps(result, allow_nan=False)

    def test_hold_expiry_recovery_and_clock(self):
        now = [10.]
        tracker = ArucoBoardTracker(clock=lambda: now[0])
        original = tracker.process(marker_image())
        image = marker_image()
        image[60:120, 60:120] = 255
        now[0] += .2
        held = tracker.process(image)
        self.assertEqual(held['status'], 'held')
        self.assertEqual(held['homography_camera_to_instrument'], original['homography_camera_to_instrument'])
        now[0] += .06
        lost = tracker.process(image)
        self.assertEqual(lost['status'], 'lost')
        self.assertIsNone(lost['homography_camera_to_instrument'])
        self.assertEqual(tracker.process(marker_image())['status'], 'valid')
        self.assertEqual(tracker.process(marker_image(), 9.)['reason'], 'invalid_timestamp')

    def test_no_markers(self):
        result = ArucoBoardTracker().process(np.zeros((480, 640, 3), np.uint8), 0)
        self.assertEqual(result['visible_ids'], [])
        self.assertIsNone(result['homography_instrument_to_camera'])

    def test_duplicates_and_degenerate_layout_clear_cache(self):
        real = ArucoBoardTracker()
        detections = real.detector.detectMarkers(marker_image())
        detector = Mock()
        tracker = ArucoBoardTracker(detector=detector)
        detector.detectMarkers.return_value = detections
        self.assertEqual(tracker.process(marker_image(), 0)['status'], 'valid')
        corners, ids, rejected = detections
        detector.detectMarkers.return_value = (list(corners) + [corners[0]], np.vstack([ids, ids[0]]), rejected)
        self.assertEqual(tracker.process(marker_image(), .01)['reason'], 'duplicate_required_ids')
        self.assertIsNone(tracker.last_valid_H)
        detector.detectMarkers.return_value = ([np.full((1, 4, 2), i*10, np.float32) for i in range(4)], np.arange(4).reshape(-1, 1), [])
        self.assertEqual(tracker.process(marker_image(), .02)['reason'], 'invalid_marker_layout')
