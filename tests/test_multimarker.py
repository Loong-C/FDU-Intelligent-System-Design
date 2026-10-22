import json
import unittest
from unittest.mock import Mock
import cv2 as cv
import numpy as np
from aruco_tracking import ArucoBoardTracker
from board_definition import BoardDefinition
from instrument_geometry import project
from tests.helpers import marker_image
from tests.plane_fixtures import six_marker_board, render_board, DEFAULT_INVERSE


class MultiMarkerTests(unittest.TestCase):
    def test_rotated_free_layout_perspective_and_rigid_motion(self):
        board = six_marker_board()
        points = [[.25, .5], [.8, .6], [-.05, .3], [1.2, .5]]
        for inverse in (DEFAULT_INVERSE, np.array([[490, -90, 200], [60, 410, 60], [.13, -.12, 1.]]),
                        np.array([[450, 95, 100], [-75, 420, 170], [-.13, .12, 1.]])):
            result = ArucoBoardTracker(board=board).process(render_board(board, inverse), 10)
            self.assertEqual(result['status'], 'valid', result)
            self.assertEqual(result['pose_quality']['correspondence_count'], 24)
            self.assertGreaterEqual(result['pose_quality']['inlier_count'], 20)
            # A hand moving with the plane retains the same board UV.
            actual = project(project(points, inverse), result['homography_camera_to_instrument'])
            np.testing.assert_allclose(actual, points, atol=.004)
            json.dumps(result, allow_nan=False)

    def test_occlusion_single_marker_loss_and_recovery(self):
        tracker = ArucoBoardTracker(board=six_marker_board())
        for i, ids in enumerate((range(4, 10), [4, 5, 7, 8], [4, 7, 8], [4, 7])):
            result = tracker.process(render_board(visible=ids), 10+i*.04)
            self.assertEqual(result['status'], 'valid', result)
        single = tracker.process(render_board(visible=[4]), 10.16)
        self.assertEqual(single['status'], 'degraded')
        self.assertEqual(single['reason'], 'single_marker_extrapolation')
        self.assertIsNotNone(single['homography_camera_to_instrument'])
        self.assertEqual(tracker.process(render_board(visible=[]), 10.2)['status'], 'held')
        lost = tracker.process(render_board(visible=[]), 10.4)
        self.assertEqual(lost['status'], 'lost')
        self.assertIsNone(lost['homography_camera_to_instrument'])
        self.assertEqual(tracker.process(render_board(), 10.5)['status'], 'valid')

    def test_legacy_learning_needs_no_new_calibration(self):
        tracker = ArucoBoardTracker(learn_legacy=True)
        self.assertEqual(tracker.process(marker_image(), 1)['status'], 'valid')
        image = marker_image()
        image[60:120, 60:120] = 255
        self.assertEqual(tracker.process(image, 1.04)['status'], 'valid')

    def test_ambiguity_bad_coordinates_outliers_and_unknown_ids(self):
        board = six_marker_board()
        real = ArucoBoardTracker(board=board)
        corners, ids, _ = real.detector.detectMarkers(render_board())
        detector = Mock()
        tracker = ArucoBoardTracker(board=board, detector=detector)
        detector.detectMarkers.return_value = (corners, ids, [])
        self.assertEqual(tracker.process(render_board(), 1)['status'], 'valid')
        detector.detectMarkers.return_value = (list(corners)+[corners[0]], np.vstack([ids, ids[0]]), [])
        result = tracker.process(render_board(), 1.1)
        self.assertEqual(result['status'], 'lost')
        self.assertEqual(result['reason'], 'duplicate_registered_ids')
        broken = [x.copy() for x in corners]
        broken[0][0, 0, 0] = np.nan
        detector.detectMarkers.return_value = (broken, ids, [])
        self.assertEqual(tracker.process(render_board(), 1.2)['reason'], 'invalid_marker_coordinates')
        broken = [x.copy() for x in corners]
        broken[0] += [80, 25]
        detector.detectMarkers.return_value = (broken, ids, [])
        result = tracker.process(render_board(), 1.3)
        self.assertEqual(result['status'], 'valid', result)  # 5 complete consistent markers survive RANSAC.
        self.assertEqual(result['pose_quality']['inlier_count'], 20)
        detector.detectMarkers.return_value = (list(corners)+[corners[0]], np.vstack([ids, [[49]]]), [])
        self.assertEqual(tracker.process(render_board(), 1.4)['pose_quality']['correspondence_count'], 24)
        broken[1] += [-90, 75]
        detector.detectMarkers.return_value = (broken, ids, [])
        self.assertNotEqual(tracker.process(render_board(), 1.5)['status'], 'valid')

    def test_coverage_and_temporal_jump_are_not_marker_counts(self):
        board = six_marker_board()
        tracker = ArucoBoardTracker(board=board)
        self.assertEqual(tracker.process(render_board(), 1)['status'], 'valid')
        moved = DEFAULT_INVERSE.copy()
        moved[0, 2] += 240
        image = render_board(inverse=moved, size=(1400, 720))
        # Same output canvas size makes the threshold independent of a resolution switch.
        tracker = ArucoBoardTracker(board=board)
        tracker.process(render_board(size=(1400, 720)), 1)
        moved[0, 2] += 110
        image = render_board(inverse=moved, size=(1400, 720))
        result = tracker.process(image, 1.02)
        self.assertEqual(result['status'], 'degraded', result)
        self.assertEqual(result['reason'], 'implausible_transform_jump')
        self.assertEqual(tracker.process(image, 1.07)['status'], 'degraded')
        self.assertEqual(tracker.process(image, 1.14)['status'], 'valid')
        tiny = {str(i): {'corners_uv': [[i*.08, 0], [i*.08+.03, 0], [i*.08+.03, .03], [i*.08, .03]]} for i in range(6)}
        compact = BoardDefinition('thin', tiny)
        result = ArucoBoardTracker(board=compact).process(render_board(compact), 0)
        self.assertNotEqual(result['status'], 'valid')
