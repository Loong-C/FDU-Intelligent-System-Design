"""Replay recorded raw frames; mock audio by default, no camera required."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board_definition import BoardDefinition
from instrument_preset import InstrumentPreset
from replay import replay_recording


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--output', required=True, help='New JSONL file; existing files are never overwritten')
    parser.add_argument('--board', help='Override physical board for algorithm/layout comparisons')
    parser.add_argument('--preset')
    parser.add_argument('--rerun-hands', action='store_true')
    parser.add_argument('--audio', choices=['mock', 'sounddevice'], default='mock')
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    result = replay_recording(args.directory, args.output,
                              BoardDefinition.load(args.board) if args.board else None,
                              InstrumentPreset.load(args.preset) if args.preset else None,
                              args.rerun_hands, args.audio, args.allow_incomplete)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
