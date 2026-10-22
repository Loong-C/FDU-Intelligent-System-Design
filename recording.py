"""Bounded asynchronous packet recording, separate from the audio callback."""
import csv
from datetime import datetime
import json
import queue
from pathlib import Path
import threading

COLUMNS = ['frame_id', 'timestamp_unix_s', 'track_id', 'handedness', 'confidence',
           'node_id', 'node_name', 'x_px', 'y_px', 'z_relative_px',
           'x_normalized', 'y_normalized', 'z_normalized', 'world_x_m', 'world_y_m', 'world_z_m',
           'instrument_u', 'instrument_v']


class Recorder:
    def __init__(self, root, capacity=128):
        self.folder = Path(root) / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.folder.mkdir(parents=True, exist_ok=False)
        self.queue = queue.Queue(maxsize=capacity)
        self.stop = threading.Event()
        self.error = None
        self.frames = 0
        self.thread = threading.Thread(target=self._run, name='packet-recorder', daemon=True)
        self.thread.start()

    def submit(self, packet):
        if self.stop.is_set() or self.error:
            return False
        try:
            self.queue.put_nowait(packet)
            return True
        except queue.Full:
            self.error = 'Recording queue full; recording stopped. Some frames were not saved.'
            self.stop.set()
            return False

    def _run(self):
        try:
            with ((self.folder/'landmarks.jsonl').open('w', encoding='utf-8') as jf,
                  (self.folder/'landmarks.csv').open('w', newline='', encoding='utf-8') as cf,
                  (self.folder/'events.jsonl').open('w', encoding='utf-8') as ef):
                writer = csv.writer(cf)
                writer.writerow(COLUMNS)
                last_event = 0
                while not self.stop.is_set() or not self.queue.empty():
                    try:
                        packet = self.queue.get(timeout=.05)
                    except queue.Empty:
                        continue
                    jf.write(json.dumps(packet, separators=(',', ':'), allow_nan=False)+'\n')
                    for hand in packet['hands']:
                        for i, name in enumerate(packet['landmark_names']):
                            uv = hand.get('landmarks_instrument_uv')
                            writer.writerow([packet['frame_id'], packet['timestamp_unix_s'], hand['track_id'],
                                             hand['handedness'], hand['confidence'], i, name,
                                             *hand['landmarks_px'][i], *hand['landmarks_normalized'][i],
                                             *hand['landmarks_world_m'][i], *(uv[i] if uv is not None else ['', ''])])
                    for event in packet.get('events', []):
                        if event['event_id'] > last_event:
                            ef.write(json.dumps(event, allow_nan=False)+'\n')
                            last_event = event['event_id']
                    self.frames += 1
                    jf.flush()
                    cf.flush()
                    ef.flush()
        except Exception as exc:
            self.error = str(exc)
            self.stop.set()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            self.error = 'Recorder is still draining after 5 seconds; check disk performance.'
