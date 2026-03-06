## Goal

Make the browser live viewer honor `max_fps=10` in practice, not just in the client request.

## Root Cause

- The WebSocket stream re-deduped repeated CDP frames after it was already pacing by `interval`, which collapsed idle streams toward low single-digit FPS.
- The live path started the screencast before rendering the placeholder page, so the stream often began from a visually blank browser state.
- Screenshot fallback disabled animations and re-captured too aggressively while waiting for CDP, which wasted time without improving frame cadence.

## Implementation

- Render the placeholder page before starting the CDP screencast.
- Preserve animation in live screenshot fallback captures.
- Pace frame emission by absolute deadlines instead of `send -> sleep(interval)`.
- Reuse the last screenshot frame while waiting for CDP instead of recapturing every frame.
- Remove the extra repeated-frame throttle so identical frames can still be emitted at the requested cadence.

## Validation

- Added regression tests for repeated-frame emission and bootstrap-frame reuse in `tests/test_browser_ws_stream_fps.py`.
- Kept failure-stop coverage green in `tests/test_browser_ws_stream_failure_stops.py`.
- Fresh verification:
  - `python -m compileall -q main.py tests`
  - `pytest -q`
- Real browser smoke:
  - Frontend displayed `10 FPS`
  - Measured last-5-second average: `10.2 FPS`
