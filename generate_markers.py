"""Generate printable ArUco IDs with a white quiet zone (default IDs 0..3)."""
import argparse
from pathlib import Path
import cv2 as cv
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids', nargs='+', type=int, default=[0, 1, 2, 3])
    args = parser.parse_args()
    if len(set(args.ids)) != len(args.ids) or any(i not in range(50) for i in args.ids):
        parser.error('Use distinct DICT_4X4_50 IDs in 0..49')
    root = Path(__file__).resolve().parent/'outputs/markers'
    root.mkdir(parents=True, exist_ok=True)
    dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_4X4_50)
    for marker_id in args.ids:
        marker = cv.aruco.generateImageMarker(dictionary, marker_id, 600)
        page = np.full((840, 800), 255, np.uint8)
        page[100:700, 100:700] = marker
        cv.putText(page, f'DICT_4X4_50 / ID {marker_id}', (150, 780), cv.FONT_HERSHEY_SIMPLEX, 1., 0, 2)
        ok, encoded = cv.imencode('.png', page)
        if not ok:
            raise RuntimeError('Marker encoding failed')
        encoded.tofile(root/f'marker_{marker_id}.png')
    print(root)
    print('Keep white margins and do not mirror prints. Free layouts: use web board calibration.')
    print('Legacy demo without calibration: marker centers in rows 0 1 / 2 3.')


if __name__ == '__main__':
    main()
