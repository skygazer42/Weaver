#!/usr/bin/env python
"""CLI helper to call /api/research and stream events.
Usage:
  python scripts/cli_research.py "your question" --host http://localhost:8000
"""
import argparse
import json
import sys

import httpx


def stream_research(query: str, host: str):
    url = f"{host.rstrip('/')}/api/research"
    with httpx.stream("POST", url, params={"query": query}, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                # format_stream_event uses "0:{json}\n"
                if line.startswith("0:"):
                    payload = json.loads(line[2:])
                    print(payload)
                else:
                    print(line)
            except Exception as e:
                print(f"[parse error] {e}: {line}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Research query text")
    parser.add_argument("--host", default="http://localhost:8000", help="Backend host")
    args = parser.parse_args()
    stream_research(args.query, args.host)


if __name__ == "__main__":
    main()
