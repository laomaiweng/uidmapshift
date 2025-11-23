import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

MAX_ID = 1 << 32


@dataclass
class ShifterOptions:
    dry_run: bool = False
    quiet: bool = False


@dataclass
class ShifterStats:
    shifted: int = 0
    skipped: int = 0


class Shifter:
    def __init__(
        self,
        uid_offset: int,
        gid_offset: int,
        exclude_uid_ranges: list[range] = list(),
        exclude_gid_ranges: list[range] = list(),
        exclude_paths: list[str] = list(),
    ):
        self.uid_offset = uid_offset
        self.gid_offset = gid_offset
        self.exclude_uid_ranges = exclude_uid_ranges
        self.exclude_gid_ranges = exclude_gid_ranges
        self.exclude_paths = exclude_paths

    def new_uid(self, uid: int) -> int:
        """Returns -1 if unchanged."""

        if any(uid in r for r in self.exclude_uid_ranges):
            return -1

        new_uid = uid + self.uid_offset
        if new_uid not in range(0, MAX_ID):
            raise ValueError(f"Invalid new UID: {uid} -> {new_uid}")

        return new_uid

    def new_gid(self, gid: int) -> int:
        """Returns -1 if unchanged."""

        if any(gid in r for r in self.exclude_gid_ranges):
            return -1

        new_gid = gid + self.gid_offset
        if new_gid not in range(0, MAX_ID):
            raise ValueError(f"Invalid new GID: {gid} -> {new_gid}")

        return new_gid

    def shift(
        self,
        path: Path,
        options: ShifterOptions = ShifterOptions(),
        stats: ShifterStats = ShifterStats(),
    ) -> bool:
        """Returns `True` if shifted."""

        if any(fnmatch.fnmatch(str(path), pat) for pat in self.exclude_paths):
            stats.skipped += 1
            if not options.quiet:
                suffix = "/" if path.is_dir() else ""
                print(f"{path}{suffix}: skip")
            return False

        try:
            stat = os.stat(path, follow_symlinks=False)
            uid = stat.st_uid
            gid = stat.st_gid
            new_uid = self.new_uid(uid)
            new_gid = self.new_gid(gid)

            if new_uid == -1 and new_gid == -1:
                stats.skipped += 1
                if not options.quiet:
                    suffix = "/" if path.is_dir() else ""
                    print(f"{path}{suffix}: {uid}:{gid} skip")
                return False

            stats.shifted += 1

            if not options.quiet:
                suffix = "/" if path.is_dir() else ""
                show_uid = uid if new_uid == -1 else new_uid
                show_gid = gid if new_gid == -1 else new_gid
                print(f"{path}{suffix}: {uid}:{gid} -> {show_uid}:{show_gid}")

            if not options.dry_run:
                os.chown(path, new_uid, new_gid, follow_symlinks=False)

            return True
        except:
            raise RuntimeError(f"Failed to shift UID/GID for: {path}")

    def run(
        self, path: str, options: ShifterOptions = ShifterOptions()
    ) -> ShifterStats:
        stats = ShifterStats()

        for root, dirs, files in os.walk(path):
            if "root" == path:
                continue

            for d in dirs:
                self.shift(Path(root) / d, options, stats)

            for f in files:
                self.shift(Path(root) / f, options, stats)

        return stats
