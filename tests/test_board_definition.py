import json
from pathlib import Path
import tempfile
import unittest
from board_definition import BoardDefinition


class BoardDefinitionTests(unittest.TestCase):
    def test_one_to_twelve_and_unclipped_coordinates(self):
        for n in range(1, 13):
            markers = {str(i): {'corners_uv': [[i-.2, 0], [i+.1, 0], [i+.1, .2], [i-.2, .2]]} for i in range(n)}
            board = BoardDefinition('test', markers)
            with tempfile.TemporaryDirectory() as root:
                path = Path(root)/'test.json'
                path.write_text(json.dumps(board.to_dict()))
                self.assertEqual(BoardDefinition.load(path).to_dict(), board.to_dict())
            self.assertEqual(board.points[0, 0], -.2)

    def test_invalid_config(self):
        valid = {'0': {'corners_uv': [[0, 0], [1, 0], [1, 1], [0, 1]]}}
        for kwargs in ({'board_id': '../bad'}, {'schema_version': 2}, {'dictionary': 'DICT_UNKNOWN'},
                       {'markers': {}}, {'markers': {'50': valid['0']}},
                       {'markers': {'0': valid['0'], '1': valid['0']}},
                       {'markers': {'0': {'corners_uv': [[0, 0], [1, 1], [0, 1], [1, 0]]}}},
                       {'markers': {'0': {'corners_uv': [[0, 0], [1, 0], [1, float('nan')], [0, 1]]}}}):
            data = dict(board_id='test', markers=valid)
            data.update(kwargs)
            with self.assertRaises(ValueError):
                BoardDefinition(**data)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'bad.json'
            path.write_text('{"board_id":"a","board_id":"b"}')
            with self.assertRaises(ValueError):
                BoardDefinition.load(path)
