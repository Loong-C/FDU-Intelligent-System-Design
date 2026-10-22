"""One board layout and one projective geometry for interaction and drawing.

Region dimensions reference MotionMuse/SMF-an; see docs/integration/BASELINE.md.
UV is a 2-D image projection, not a contact or depth measurement.
"""
from dataclasses import dataclass
import numpy as np

CHORDS = ('C', 'G', 'Am', 'F')
BOARD_UV = np.float32(((0, 0), (1, 0), (0, 1), (1, 1)))
PERIMETER = (0, 1, 3, 2)


def raw_to_display_xy(points, width, mirrored):
    result = np.asarray(points, dtype=np.float64).copy()
    if mirrored:
        result[..., 0] = width - 1 - result[..., 0]
    return result


display_to_raw_xy = raw_to_display_xy  # A horizontal reflection is its own inverse.


def project(points, matrix):
    """Return Nx2, or None for invalid H/points/near-zero denominator. Never clip UV."""
    if matrix is None:
        return None
    try:
        points = np.asarray(points, dtype=np.float64)
        matrix = np.asarray(matrix, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2 or matrix.shape != (3, 3):
            return None
        if not np.isfinite(points).all() or not np.isfinite(matrix).all():
            return None
        scale = np.max(np.abs(matrix))
        if scale == 0:
            return None
        matrix = matrix / scale
        homogeneous = np.column_stack((points, np.ones(len(points)))) @ matrix.T
        denominator = homogeneous[:, 2]
        if np.any(np.abs(denominator) < 1e-10):
            return None
        with np.errstate(over='ignore', invalid='ignore'):
            result = homogeneous[:, :2] / denominator[:, None]
        return result if np.isfinite(result).all() else None
    except (TypeError, ValueError):
        return None


camera_to_instrument_uv = project


def instrument_to_display_xy(points, inverse, width, mirrored):
    raw = project(points, inverse)
    return None if raw is None else raw_to_display_xy(raw, width, mirrored)


@dataclass(frozen=True)
class InstrumentLayout:
    """flip_u reflects regions, never anatomical handedness or published board UV."""
    flip_u: bool = False
    chord_u: tuple = (.04, .60)
    chord_v: tuple = (.20, .80)
    strum_u: tuple = (.68, .90)
    strum_v: tuple = (.15, .85)
    axis_v: float = .5

    def local(self, point):
        u, v = point
        return (1 - u if self.flip_u else u), v

    def chord_at(self, point, margin=0.0):
        u, v = self.local(point)
        if not self.chord_u[0] <= u <= self.chord_u[1] or not self.chord_v[0] <= v <= self.chord_v[1]:
            return None
        width = (self.chord_u[1] - self.chord_u[0]) / len(CHORDS)
        index = min(int((u - self.chord_u[0]) / width), len(CHORDS) - 1)
        lo = self.chord_u[0] + index * width
        if not lo + margin <= u <= lo + width - margin:
            return None
        return CHORDS[index]

    def in_strum_band(self, point):
        u, v = self.local(point)
        return self.strum_u[0] <= u <= self.strum_u[1] and self.strum_v[0] <= v <= self.strum_v[1]

    def _polygon(self, x0, x1, y0, y1):
        return [list(self.local(p)) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    def regions(self):
        width = (self.chord_u[1] - self.chord_u[0]) / len(CHORDS)
        chords = {name: self._polygon(self.chord_u[0] + i * width,
                                     self.chord_u[0] + (i + 1) * width, *self.chord_v)
                  for i, name in enumerate(CHORDS)}
        return {'name': 'flip-u' if self.flip_u else 'standard', 'chords': chords,
                'strum': self._polygon(*self.strum_u, *self.strum_v),
                'axis': [list(self.local((u, self.axis_v))) for u in self.strum_u]}


def fuse_hands(packet, instrument):
    """Mutate only additive schema-v2 fields; retain A's display-coordinate arrays."""
    matrix = instrument['homography_camera_to_instrument']
    for hand in packet['hands']:
        raw = display_to_raw_xy(np.asarray(hand['landmarks_px'])[:, :2],
                                packet['frame_width'], packet['mirrored'])
        uv = project(raw, matrix)
        hand['landmarks_instrument_uv'] = uv.tolist() if uv is not None and uv.shape == (21, 2) else None
        hand['projection_status'] = 'valid' if hand['landmarks_instrument_uv'] is not None else 'unavailable'
    packet.update(schema_version=2, instrument=instrument)


def overlay_polygons(packet, layout):
    """Return the exact polygons used by both the layout hit-test and the renderer."""
    regions = layout.regions()
    result = {}
    shapes = dict(regions['chords'], strum=regions['strum'], axis=regions['axis'],
                  board=BOARD_UV[list(PERIMETER)])
    for name, points in shapes.items():
        projected = instrument_to_display_xy(points, packet['instrument']['homography_instrument_to_camera'],
                                             packet['frame_width'], packet['mirrored'])
        result[name] = None if projected is None else projected.tolist()
    return result
