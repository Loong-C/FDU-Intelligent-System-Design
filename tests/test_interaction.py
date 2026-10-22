import json
import unittest
from instrument_logic import InstrumentLogic, InteractionConfig
from instrument_geometry import InstrumentLayout
from tests.helpers import packet


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.
        self.logic = InstrumentLogic(clock=lambda: self.now)

    def step(self, t, **kwargs):
        self.now = t
        p = packet(t, **kwargs)
        state, events = self.logic.process(p)
        json.dumps([state, events], allow_nan=False)
        return state, events

    def arm(self):
        self.step(0)
        state, _ = self.step(.11)
        self.assertTrue(state['chord_valid'])

    def test_time_dwell_and_four_chords(self):
        for chord, u in zip(('C', 'G', 'Am', 'F'), (.1, .25, .39, .53)):
            self.setUp()
            self.assertFalse(self.step(0, left=(u, .5))[0]['chord_valid'])
            self.assertFalse(self.step(.09, left=(u, .5))[0]['chord_valid'])
            state, _ = self.step(.10, left=(u, .5))
            self.assertEqual(state['current_chord'], chord)
            self.assertTrue(state['chord_valid'])

    def test_stationary_and_boundary_jitter(self):
        self.arm()
        for i in range(1, 101):
            state, events = self.step(.11+i*.02, left=(.18+(-1)**i*.005, .5), right=(.78, .5+(-1)**i*.025))
            self.assertEqual(state['current_chord'], 'C')
            self.assertEqual(events, [])
        self.step(2.15, left=(.25, .5))
        self.assertEqual(self.step(2.26, left=(.25, .5))[0]['current_chord'], 'G')

    def test_fast_down_up_once_and_cooldown(self):
        self.arm()
        self.step(.15, right=(.78, .48))
        _, events = self.step(.19, right=(.78, .65))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['direction'], 'down')
        self.assertEqual(events[0]['chord'], 'C')
        self.assertTrue(1 <= events[0]['velocity'] <= 127)
        self.assertEqual(self.step(.23, right=(.78, .3))[1], [])
        self.step(.27, right=(.78, .65))
        self.step(.38, right=(.78, .65))
        _, events = self.step(.43, right=(.78, .3))
        self.assertEqual(events[0]['direction'], 'up')
        self.assertEqual(events[0]['event_id'], 2)

    def test_slow_crossing(self):
        self.arm()
        for i in range(1, 31):
            self.assertEqual(self.step(.11+i*.1, right=(.78, .3+i*.01))[1], [])

    def test_loss_board_hand_and_recovery(self):
        for failure in ({'board': 'held'}, {'board': 'lost'}, {'left': None}, {'right': None}):
            self.setUp()
            self.arm()
            self.assertEqual(self.step(.15, **failure)[1], [])
            self.assertEqual(self.step(.2, right=(.78, .65))[1], [])
            self.assertEqual(self.step(.31, right=(.78, .65))[1], [])
            self.assertEqual(self.step(.36, right=(.78, .3))[1][0]['direction'], 'up')

    def test_stale_reordered_large_gap_and_track_change(self):
        self.arm()
        p = packet(.15, right=(.78, .65))
        p['hands'][1]['track_id'] = 3
        self.now = .15
        self.assertEqual(self.logic.process(p)[1], [])
        self.assertEqual(self.logic.process(p)[1], [])
        self.assertEqual(self.step(.8, right=(.78, .65))[1], [])
        self.now = 2.
        self.assertEqual(self.logic.process(packet(.9, right=(.78, .3)))[1], [])

    def test_invalid_points_confidence_and_identity(self):
        for kind in ('nan', 'low', 'duplicate', 'switch', 'jump'):
            self.setUp()
            self.arm()
            p = packet(.15, right=(.78, .65))
            if kind == 'nan':
                p['hands'][1]['landmarks_instrument_uv'][8][0] = float('nan')
            elif kind == 'low':
                p['hands'][0]['confidence'] = .1
            elif kind == 'duplicate':
                p['hands'][1]['handedness'] = 'Left'
            elif kind == 'switch':
                p['hands'][0]['handedness'], p['hands'][1]['handedness'] = 'Right', 'Left'
            else:
                p['hands'][1]['landmarks_instrument_uv'][8][1] = .85
            self.now = .15
            state, events = self.logic.process(p)
            self.assertEqual(events, [], kind)
            json.dumps(state, allow_nan=False)

    def test_sample_rate_independence_and_dropped_frames(self):
        for fps in (10, 20, 30, 60):
            self.setUp()
            events = []
            for i in range(int(fps*.8)):
                t = i/fps
                v = .3 if t < .2 else min(.7, .3+(t-.2)*2)
                events.extend(self.step(t, right=(.78, v))[1])
            self.assertEqual(len(events), 1, fps)
            self.assertEqual(events[0]['direction'], 'down')

    def test_flip_layout_keeps_anatomical_roles(self):
        self.logic = InstrumentLogic(InstrumentLayout(flip_u=True), clock=lambda: self.now)
        self.step(0, left=(.9, .5), right=(.22, .3))
        self.step(.11, left=(.9, .5), right=(.22, .3))
        self.assertEqual(self.step(.2, left=(.9, .5), right=(.22, .65))[1][0]['chord'], 'C')

    def test_bad_config(self):
        with self.assertRaises(ValueError):
            InteractionConfig(max_gap_s=0)
