"""Validated physical plane definitions. No instrument or audio assumptions."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import cv2 as cv
import numpy as np


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('Name must contain 1–64 ASCII letters, digits, underscores or hyphens')
    if value.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
        raise ValueError('Reserved filename')
    return value


def polygon(value, label='polygon', convex=False):
    try:
        p = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}: expected finite Nx2 coordinates') from exc
    if p.ndim != 2 or p.shape[1] != 2 or not 3 <= len(p) <= 256 or not np.isfinite(p).all():
        raise ValueError(f'{label}: expected 3–256 finite 2D points')
    if np.max(np.abs(p)) > 1e6 or len(np.unique(p, axis=0)) != len(p):
        raise ValueError(f'{label}: duplicate or numerically excessive coordinates')
    if abs(cv.contourArea(p.astype(np.float32))) < 1e-8:
        raise ValueError(f'{label}: degenerate area')
    def cross(a, b, c):
        d, e = b-a, c-a
        return d[0]*e[1]-d[1]*e[0]
    def intersects(a, b, c, d):
        return (max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0])) and
                max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1])) and
                cross(a, b, c)*cross(a, b, d) <= 0 and cross(c, d, a)*cross(c, d, b) <= 0)
    for i in range(len(p)):
        for j in range(i+1, len(p)):
            if j == i+1 or (i == 0 and j == len(p)-1):
                continue
            if intersects(p[i], p[(i+1) % len(p)], p[j], p[(j+1) % len(p)]):
                raise ValueError(f'{label}: self-intersecting polygon')
    if convex and not cv.isContourConvex(p.astype(np.float32)):
        raise ValueError(f'{label}: expected a convex quadrilateral in perimeter order')
    return p


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream, object_pairs_hook=_unique_object)


@dataclass(frozen=True)
class BoardDefinition:
    board_id: str
    markers: dict
    dictionary: str = 'DICT_4X4_50'
    outline_uv: object = None
    metadata: dict = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self):
        safe_name(self.board_id)
        if self.schema_version != 1:
            raise ValueError('Unsupported board schema_version (expected 1)')
        if not isinstance(self.dictionary, str) or not re.fullmatch(r'DICT_[A-Z0-9_]+', self.dictionary):
            raise ValueError('Invalid ArUco dictionary')
        constant = getattr(cv.aruco, self.dictionary, None)
        if not isinstance(constant, int):
            raise ValueError('Unknown ArUco dictionary')
        size = len(cv.aruco.getPredefinedDictionary(constant).bytesList)
        if not isinstance(self.markers, dict) or not 1 <= len(self.markers) <= size:
            raise ValueError(f'Expected 1–{size} distinct markers')
        clean = {}
        for key, entry in self.markers.items():
            if not re.fullmatch(r'0|[1-9][0-9]*', str(key)) or not 0 <= int(key) < size:
                raise ValueError(f'Marker ID outside dictionary: {key}')
            if int(key) in clean:
                raise ValueError('Duplicate marker ID')
            if not isinstance(entry, dict):
                raise ValueError('Marker entry must contain corners_uv')
            p = polygon(entry.get('corners_uv'), f'marker {key}', convex=True)
            if len(p) != 4 or cv.contourArea(p.astype(np.float32), oriented=True) <= 0:
                raise ValueError('Marker corners must follow OpenCV encoded TL, TR, BR, BL order; do not sort them')
            edges = np.linalg.norm(np.roll(p, -1, axis=0)-p, axis=1)
            if edges.min()/edges.max() < .005:
                raise ValueError('Numerically unstable marker geometry')
            clean[int(key)] = {'corners_uv': p.tolist()}
        # Physical printed markers cannot occupy overlapping plane area.
        keys = list(clean)
        for i, a in enumerate(keys):
            for b in keys[i+1:]:
                area, _ = cv.intersectConvexConvex(np.float32(clean[a]['corners_uv']), np.float32(clean[b]['corners_uv']))
                if area > 1e-8:
                    raise ValueError(f'Overlapping marker definitions: {a}, {b}')
        object.__setattr__(self, 'markers', clean)
        if self.outline_uv is not None:
            object.__setattr__(self, 'outline_uv', polygon(self.outline_uv, 'outline_uv').tolist())
        if not isinstance(self.metadata, dict):
            raise ValueError('metadata must be an object')
        json.dumps(self.metadata, allow_nan=False)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError('Board definition must be an object')
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError(f'Invalid board fields: {exc}') from exc

    @classmethod
    def load(cls, path):
        return cls.from_dict(read_json(path))

    def to_dict(self):
        return {'schema_version': self.schema_version, 'board_id': self.board_id,
                'dictionary': self.dictionary, 'markers': {str(k): v for k, v in self.markers.items()},
                'outline_uv': self.outline_uv, 'metadata': self.metadata}

    @property
    def points(self):
        return np.concatenate([entry['corners_uv'] for entry in self.markers.values()]).astype(np.float64)
