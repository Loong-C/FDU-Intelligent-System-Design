"""Compare old four-center tracking and joint corners on identical synthetic input."""
import argparse
import json
from pathlib import Path
import platform
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2 as cv
import numpy as np
from aruco_tracking import ArucoBoardTracker, LegacyArucoBoardTracker
from synthetic_input import board_image
from tests.plane_fixtures import render_board, six_marker_board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=300)
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.iterations < 10:
        parser.error('Use at least 10 iterations')
    cv.setNumThreads(4)
    image = board_image()
    cases = [('legacy_four_centers', LegacyArucoBoardTracker(), image),
             ('joint_four_markers', ArucoBoardTracker(learn_legacy=True), image),
             ('joint_six_markers_960x720', ArucoBoardTracker(board=six_marker_board()), render_board())]
    report = dict(platform=platform.platform(), python=platform.python_version(), opencv=cv.__version__,
                  numpy=np.__version__, iterations=args.iterations, opencv_threads=cv.getNumThreads(),
                  input='synthetic raster images, no camera or hand inference', jetson='NOT TESTED', results={})
    for name, tracker, frame in cases:
        samples = []
        for i in range(args.iterations+20):
            start = time.perf_counter()
            result = tracker.process(frame, i/30)
            elapsed = (time.perf_counter()-start)*1000
            if result['status'] != 'valid':
                raise RuntimeError(result['reason'])
            if i >= 20:
                samples.append(elapsed)
        report['results'][name] = dict(p50_ms=float(np.median(samples)), p95_ms=float(np.percentile(samples, 95)))
    report['same_input_overhead_p50_ms'] = report['results']['joint_four_markers']['p50_ms']-report['results']['legacy_four_centers']['p50_ms']
    text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(text+'\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
