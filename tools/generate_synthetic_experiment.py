"""Generate moving-plane/occlusion experimental data with explicitly scripted hands."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2 as cv
import numpy as np
from aruco_tracking import ArucoBoardTracker
from hand_tracking import NAMES, EDGES
from instrument_geometry import project
from instrument_logic import InstrumentLogic
from pipeline import PerceptionPipeline
from recording import Recorder
from replay import analyze_packets
from tests.helpers import hand
from tests.plane_fixtures import render_board, six_marker_board, DEFAULT_INVERSE


class ScriptedPlaneHands:
    def __init__(self):
        self.frame_id = 0
        self.inverse = DEFAULT_INVERSE

    def process(self, raw, timestamp):
        t = self.frame_id/30
        self.frame_id += 1
        hands = []
        for role, point, tid in [('Left', [.11+int(t/1.5)%4*.14, .5], 1), ('Right', [.78, .5-.2*np.cos(t*6)], 2)]:
            h = hand(role, point, tid)
            xy = project(h['landmarks_instrument_uv'], self.inverse)
            xyz = np.column_stack([xy, np.zeros(21)])
            h['landmarks_px'] = xyz.tolist()
            h['landmarks_normalized'] = (xyz/[raw.shape[1], raw.shape[0], raw.shape[1]]).tolist()
            hands.append(h)
        return raw.copy(), dict(frame_id=self.frame_id, timestamp_unix_s=timestamp, mirrored=False,
                                frame_width=raw.shape[1], frame_height=raw.shape[0], hands=hands,
                                landmark_names=NAMES, connections=EDGES, inference_ms=0., source='synthetic',
                                simulation_notice='Scripted nodes on a generated moving plane; no model or camera performance claim')


def generate(root, frames=210):
    cv.setNumThreads(4)
    now = [100000.]
    hands = ScriptedPlaneHands()
    pipeline = PerceptionPipeline(hands=hands, board=ArucoBoardTracker(board=six_marker_board()),
                                  logic=InstrumentLogic(clock=lambda: now[0]))
    recorder = Recorder(root, raw_frames=True)
    packets = []
    try:
        for i in range(frames):
            t = i/30
            now[0] = 100000+t
            inverse = DEFAULT_INVERSE.copy()
            inverse[0, 2] += 30*np.sin(t)
            inverse[1, 2] += 15*np.cos(t)
            inverse[2, :2] = [.025*np.sin(t), .02*np.cos(t)]
            hands.inverse = inverse
            visible = list(range(4, 10)) if t < 1 or t >= 5 else [4, 5, 7, 8] if t < 2 else [4, 7] if t < 3 else [4] if t < 4 else []
            raw = render_board(inverse=inverse, visible=visible)
            _, p = pipeline.process(raw, 1700000000+t, now[0])
            # Offline generator can pace itself; the live recorder always remains non-blocking.
            while recorder.queue.qsize() > 8 and not recorder.error:
                time.sleep(.005)
            if not recorder.submit(p, raw, pipeline.configuration()):
                raise RuntimeError(recorder.error)
            packets.append(p)
    finally:
        recorder.close()
    if recorder.error:
        raise RuntimeError(recorder.error)
    report = analyze_packets(packets)
    (recorder.folder/'analysis.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return recorder.folder, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]/'outputs'))
    parser.add_argument('--frames', type=int, default=210)
    args = parser.parse_args()
    if args.frames < 1:
        parser.error('--frames must be positive')
    folder, report = generate(args.root, args.frames)
    print(json.dumps(dict(folder=str(folder), analysis=report), indent=2))
