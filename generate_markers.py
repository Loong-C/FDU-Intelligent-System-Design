"""Generate printable DICT_4X4_50 IDs 0..3 with a white quiet zone."""
from pathlib import Path
import cv2 as cv
import numpy as np


def main():
    root = Path(__file__).resolve().parent/'outputs/markers'
    root.mkdir(parents=True, exist_ok=True)
    dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_4X4_50)
    for marker_id in range(4):
        marker = cv.aruco.generateImageMarker(dictionary, marker_id, 600)
        page = np.full((840, 800), 255, np.uint8)
        page[100:700, 100:700] = marker
        cv.putText(page, f'DICT_4X4_50 / ID {marker_id}', (150, 780), cv.FONT_HERSHEY_SIMPLEX, 1., 0, 2)
        ok, encoded = cv.imencode('.png', page)
        if not ok:
            raise RuntimeError('Marker encoding failed')
        encoded.tofile(root/f'marker_{marker_id}.png')
    print(root)
    print('Place marker centers in rows: 0 1 / 2 3. Keep the white margins. Do not mirror the print.')


if __name__ == '__main__':
    main()
