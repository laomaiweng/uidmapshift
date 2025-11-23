import argparse
import sys

from .shifter import Shifter, ShifterOptions


def _parse_range(s: str) -> range:
    if "-" in s:
        sstart, send = s.split("-", maxsplit=1)
        start = int(sstart, base=0) if len(sstart) > 0 else 0
        end = (int(send, base=0) + 1) if len(send) > 0 else 1 << 32
    else:
        start = int(s, base=0)
        end = start + 1
    return range(start, end)


def _parse_offsets(s: str) -> tuple[int, int]:
    if ":" in s:
        uid, gid = [int(ss, base=0) for ss in s.split(":", maxsplit=1)]
    else:
        uid = gid = int(s, base=0)
    return (uid, gid)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shift UIDs/GIDs of a file hierarchy. For use in managing storage for LXC priv/unpriv containers."
    )
    parser.add_argument(
        "-e",
        "--exclude-uid-range",
        type=_parse_range,
        action="append",
        default=list(),
        help="range of UIDs to exclude from shifting (cumulative, inclusive, format: start[-end])",
    )
    parser.add_argument(
        "-E",
        "--exclude-gid-range",
        type=_parse_range,
        action="append",
        default=list(),
        help="range of GIDs to exclude from shifting (cumulative, inclusive, format: star[-end])",
    )
    parser.add_argument(
        "-P",
        "--exclude-path",
        action="append",
        default=list(),
        help="path to exclude from shifting (cumulative)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="list the UID/GID shifts that would be performed but do not actually shift anything",
    )
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="don't perform an implicit dry-run before the actual shift operation",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="do not list the paths whose UIDs/GIDs are shifted",
    )
    parser.add_argument(
        "offset",
        type=_parse_offsets,
        metavar="uid_offset[:gid_offset]",
        help="offset to shift UIDs/GIDs by",
    )
    parser.add_argument(
        "path", nargs="?", default=".", help="path under which to shift UIDs/GIDs"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    uid_offset, gid_offset = args.offset
    opts = ShifterOptions(args.dry_run, args.quiet)
    shifter = Shifter(
        uid_offset,
        gid_offset,
        args.exclude_uid_range,
        args.exclude_gid_range,
        args.exclude_path,
    )

    if not args.dry_run:
        if not args.yolo:
            # Do a dry run first to weed out any obvious issues.
            # Obviously this is not fool-proof as it can fall victim to TOCTOU issues.
            print("[+] Performing sanity-check dry-run...", file=sys.stderr)
            dry_opts = ShifterOptions(dry_run=True, quiet=True)
            dry_stats = shifter.run(args.path, options=dry_opts)
            print(
                f"[+] Dry-run shifted files/dirs: {dry_stats.shifted}", file=sys.stderr
            )
            print(
                f"[+] Dry-run skipped files/dirs: {dry_stats.skipped}", file=sys.stderr
            )
            print("[+] All good, doing the real thing now", file=sys.stderr)
        else:
            print("[!] Leeeeroy Jenkins!", file=sys.stderr)

    stats = shifter.run(args.path, options=opts)
    print(f"[+] Shifted files/dirs: {stats.shifted}", file=sys.stderr)
    print(f"[+] Skipped files/dirs: {stats.skipped}", file=sys.stderr)
