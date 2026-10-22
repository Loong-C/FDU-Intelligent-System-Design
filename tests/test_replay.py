import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cv2 as cv
import numpy as np
from aruco_tracking import ArucoBoardTracker
from instrument_logic import InstrumentLogic
from pipeline import PerceptionPipeline
from recording import Recorder
from replay import replay_recording, json_lines, analyze_packets
from synthetic_input import SyntheticHandTracker, board_image
from tests.helpers import packet


class RecordingReplayTests(unittest.TestCase):
    def test_lossless_alignment_replay_states_clock_and_mock_audio(self):
        with tempfile.TemporaryDirectory() as root:
            now = [100000.]
            pipeline = PerceptionPipeline(hands=SyntheticHandTracker(), logic=InstrumentLogic(clock=lambda: now[0]))
            recorder = Recorder(root, capacity=16, raw_frames=True)
            expected = []
            # Time is historical for the current process, but valid against controlled clocks.
            for i in range(18):
                now[0] = 100000+i*.08
                raw = board_image()
                if i in (8, 9):
                    raw[45:435, 45:595] = 255
                if i in (10, 11, 12, 13, 14):
                    raw[:] = 255
                _, p = pipeline.process(raw, 1000+i*.08, now[0])
                self.assertTrue(recorder.submit(p, raw, pipeline.configuration()))
                expected.append(p['instrument']['status'])
            recorder.close()
            self.assertIsNone(recorder.error)
            manifest = json.loads((recorder.folder/'manifest.json').read_text())
            self.assertTrue(manifest['complete'])
            output = Path(root)/'replay.jsonl'
            with patch('audio_engine.SoundDeviceBackend.start', side_effect=AssertionError('Real sound forbidden')):
                report = replay_recording(recorder.folder, output)
            replayed = list(json_lines(output))
            self.assertEqual([p['instrument']['status'] for p in replayed], expected)
            self.assertEqual([p['frame_id'] for p in replayed], list(range(1, 19)))
            self.assertEqual(replayed[0]['timestamp_monotonic_s'], 1.)
            self.assertTrue(all(p['interaction']['reason'] != 'stale_or_out_of_order_frame' for p in replayed))
            self.assertEqual(report['audio']['status'], 'mock')
            self.assertGreater(report['generated_events'], 0)
            summary = analyze_packets(replayed)
            self.assertTrue(summary['recovery_durations_s'])
            self.assertIn('held', summary['state_counts'])
            with self.assertRaises(FileExistsError):
                replay_recording(recorder.folder, output)
            index = list(json_lines(recorder.folder/'frames.jsonl'))
            index[0]['frame_id'] = 99
            (recorder.folder/'frames.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in index))
            with self.assertRaisesRegex(ValueError, 'not aligned'):
                replay_recording(recorder.folder, Path(root)/'bad.jsonl')

    def test_recording_started_while_held_preserves_pose_age(self):
        with tempfile.TemporaryDirectory() as root:
            pipeline = PerceptionPipeline(hands=SyntheticHandTracker())
            raw = board_image()
            pipeline.process(raw, 1000., 100000.)
            raw[:] = 255
            _, p = pipeline.process(raw, 1000.1, 100000.1)
            recorder = Recorder(root, raw_frames=True)
            recorder.submit(p, raw, pipeline.configuration())
            recorder.close()
            output = Path(root)/'held.jsonl'
            replay_recording(recorder.folder, output)
            result = list(json_lines(output))[0]
            self.assertEqual(result['instrument']['status'], 'held')
            self.assertAlmostEqual(result['instrument']['homography_age_s'], .1)

    def test_mutable_frames_are_copied_and_default_is_data_only(self):
        with tempfile.TemporaryDirectory() as root:
            raw = board_image()
            original = raw.copy()
            p = packet(1)
            recorder = Recorder(root, raw_frames=True)
            self.assertTrue(recorder.submit(p, raw))
            raw[:] = 0
            p['frame_id'] = 9999
            recorder.close()
            index = list(json_lines(recorder.folder/'frames.jsonl'))[0]
            saved = cv.imdecode(np.fromfile(recorder.folder/index['path'], np.uint8), cv.IMREAD_COLOR)
            np.testing.assert_array_equal(saved, original)
            self.assertEqual(index['frame_id'], 1001)
            plain = Recorder(root)
            plain.submit(packet(1))
            plain.close()
            self.assertFalse((plain.folder/'frames').exists())

    def test_encoding_failure_and_queue_overflow_are_not_complete(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('recording.cv.imencode', return_value=(False, None)):
                recorder = Recorder(root, raw_frames=True)
                recorder.submit(packet(1), board_image())
                recorder.close()
            manifest = json.loads((recorder.folder/'manifest.json').read_text())
            self.assertFalse(manifest['complete'])
            self.assertIn('encoding', manifest['error'])
            self.assertEqual(list(json_lines(recorder.folder/'frames.jsonl'))[0]['status'], 'failed')
            with patch('recording.threading.Thread.start'):
                full = Recorder(root, capacity=1, raw_frames=True)
            self.assertTrue(full.submit(packet(1), board_image()))
            self.assertFalse(full.submit(packet(2), board_image()))
            full._run()  # Deterministic drain after deliberately preventing the worker start.
            manifest = json.loads((full.folder/'manifest.json').read_text())
            self.assertFalse(manifest['complete'])
            self.assertEqual(manifest['dropped_frames'], [{'frame_id': 2001, 'reason': 'queue_full'}])
