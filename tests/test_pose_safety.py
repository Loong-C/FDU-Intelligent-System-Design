import unittest
from instrument_geometry import fuse_hands, legacy_packet
from instrument_logic import InstrumentLogic
from tests.helpers import packet


class PoseSafetyTests(unittest.TestCase):
    def test_projection_semantics_and_explicit_v2_adapter(self):
        for status in ('valid', 'degraded', 'held', 'lost'):
            p = packet(0)
            instrument = {'status': status, 'homography_camera_to_instrument': None if status == 'lost' else
                          [[1/640, 0, 0], [0, 1/480, 0], [0, 0, 1]]}
            fuse_hands(p, instrument)
            self.assertEqual(p['schema_version'], 3)
            for hand in p['hands']:
                self.assertEqual(hand['projection_available'], status != 'lost')
                self.assertEqual(hand['projection_status'], status if status != 'lost' else 'unavailable')
                self.assertEqual(hand['interaction_eligible'], status == 'valid')
            v2 = legacy_packet(p)
            self.assertEqual(v2['schema_version'], 2)
            self.assertEqual(v2['hands'][0]['projection_status'], 'valid' if status != 'lost' else 'unavailable')
            self.assertEqual(p['instrument']['status'], status)  # Adapter never mutates live data.

    def test_all_unreliable_states_reset_chord_and_strum(self):
        for failure in ('degraded', 'held', 'lost'):
            now = [0.]
            logic = InstrumentLogic(clock=lambda: now[0])
            def step(t, **kwargs):
                now[0] = t
                return logic.process(packet(t, **kwargs))
            step(0)
            self.assertTrue(step(.11)[0]['chord_valid'])
            self.assertEqual(step(.15, board=failure, right=(.78, .65))[1], [])
            self.assertFalse(step(.2, right=(.78, .65))[0]['chord_valid'])
            self.assertEqual(step(.31, right=(.78, .65))[1], [])
            self.assertEqual(step(.36, right=(.78, .3))[1][0]['direction'], 'up')
