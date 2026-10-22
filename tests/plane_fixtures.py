"""Public, deterministic synthetic plane; no personal imagery or camera needed."""
import cv2 as cv
import numpy as np
from board_definition import BoardDefinition
from instrument_geometry import project


def six_marker_board():
    centers = [(.12, .13), (.77, .12), (.42, .36), (.82, .73), (.10, .79), (1.15, .46)]
    angles = [0, 24, 90, -32, 170, 45]
    markers = {}
    for i, (center, angle) in enumerate(zip(centers, angles)):
        a = np.deg2rad(angle)
        rotation = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        p = np.array([[-.06, -.06], [.06, -.06], [.06, .06], [-.06, .06]]) @ rotation.T + center
        markers[str(i+4)] = {'corners_uv': p.tolist()}
    return BoardDefinition('synthetic_six', markers,
                           outline_uv=[[-.1, -.05], [.95, -.05], [1.35, .45], [.95, 1.05], [-.1, 1.05]],
                           metadata={'source': 'programmatically generated; not a measured physical board'})


DEFAULT_INVERSE = np.array([[600., 0, 100], [0, 500., 90], [0, 0, 1.]])


def render_board(board=None, inverse=None, visible=None, size=(960, 720)):
    board = board or six_marker_board()
    inverse = DEFAULT_INVERSE if inverse is None else inverse
    image = np.full((size[1], size[0], 3), 255, np.uint8)
    dictionary = cv.aruco.getPredefinedDictionary(getattr(cv.aruco, board.dictionary))
    for marker_id, entry in board.markers.items():
        if visible is not None and marker_id not in visible:
            continue
        marker = cv.aruco.generateImageMarker(dictionary, marker_id, 120)
        target = project(entry['corners_uv'], inverse).astype(np.float32)
        transform = cv.getPerspectiveTransform(np.float32([[0, 0], [119, 0], [119, 119], [0, 119]]), target)
        layer = cv.warpPerspective(marker, transform, size, borderValue=255)
        image = np.minimum(image, cv.cvtColor(layer, cv.COLOR_GRAY2BGR))
    return image
