"""Shared high-resolution monotonic clock domain for capture, logic and audio.

Python 3.12 on Windows time.monotonic() can have ~16ms resolution. perf_counter
is monotonic and uses the high-resolution performance counter on that platform.
Do not compare these timestamps with wall time or another clock's epoch.
"""
from time import perf_counter as monotonic_s
