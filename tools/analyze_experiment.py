"""Print reproducible tracking/latency summaries from recorded or replayed JSONL."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay import analyze_packets, json_lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packets', help='landmarks.jsonl or replay output')
    parser.add_argument('--output')
    args = parser.parse_args()
    text = json.dumps(analyze_packets(json_lines(args.packets)), indent=2, allow_nan=False)
    if args.output:
        Path(args.output).write_text(text+'\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
