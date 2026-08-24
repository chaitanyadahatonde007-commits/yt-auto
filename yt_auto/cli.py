"""CLI: python -m yt_auto.cli search "python tutorial" """

from __future__ import annotations

import argparse
import json
import sys

from yt_auto.client import channel_details, search_videos, video_details


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="yt-auto", description="YouTube Data API helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="Search public videos (100 quota units)")
    s.add_argument("query")
    s.add_argument("-n", "--max", type=int, default=5)

    v = sub.add_parser("video", help="Video stats (1 unit per id)")
    v.add_argument("ids", nargs="+")

    c = sub.add_parser("channel", help="Channel stats")
    c.add_argument("handle_or_id")

    args = p.parse_args(argv)
    if args.cmd == "search":
        data = search_videos(args.query, args.max)
    elif args.cmd == "video":
        data = video_details(args.ids)
    else:
        h = args.handle_or_id
        if h.startswith("UC") and len(h) >= 20:
            data = channel_details(channel_id=h)
        else:
            data = channel_details(for_username=h)
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
