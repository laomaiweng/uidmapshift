import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

import posix1e

MAX_ID = 1 << 32


@dataclass
class ShifterOptions:
    shift_owner: bool = True
    shift_acl: bool = True
    dry_run: bool = False
    quiet: bool = False


@dataclass
class ShifterStats:
    shifted_paths: int = 0
    shifted_uids: int = 0
    shifted_gids: int = 0
    shifted_acls: int = 0
    shifted_default_acls: int = 0
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

    def shift_acl(self, acl: posix1e.ACL, is_default: bool) -> list[str]:
        """Returns the string description of the entries modified in the ACL."""

        prefix = "d:" if is_default else ""
        modified = []
        for entry in acl:
            match entry.tag_type:
                case posix1e.ACL_USER:
                    entry_uid = entry.qualifier
                    new_entry_uid = self.new_uid(entry_uid)
                    if new_entry_uid != -1:
                        modified.append(
                            f"{prefix}u:{entry_uid}:{str(entry.permset)} -> {prefix}u:{new_entry_uid}:{str(entry.permset)}"
                        )
                        entry.qualifier = new_entry_uid
                case posix1e.ACL_GROUP:
                    entry_gid = entry.qualifier
                    new_entry_gid = self.new_gid(entry_gid)
                    if new_entry_gid != -1:
                        modified.append(
                            f"{prefix}g:{entry_gid}:{str(entry.permset)} -> {prefix}g:{new_entry_gid}:{str(entry.permset)}"
                        )
                        entry.qualifier = new_entry_gid

        return modified

    def shift(
        self,
        path: Path,
        options: ShifterOptions = ShifterOptions(),
        stats: ShifterStats = ShifterStats(),
    ) -> bool:
        """Returns `True` if shifted."""

        is_dir = path.is_dir(follow_symlinks=False)

        if any(fnmatch.fnmatch(str(path), pat) for pat in self.exclude_paths):
            stats.skipped += 1
            if not options.quiet:
                suffix = "/" if is_dir else ""
                print(f"{path}{suffix}: skip")
            return False

        try:
            new_uid = -1
            new_gid = -1
            new_acl = False
            new_default_acl = False

            acl = None
            default_acl = None
            modified_acl_entries = []
            modified_default_acl_entries = []

            stat = os.stat(path, follow_symlinks=False)
            uid = stat.st_uid
            gid = stat.st_gid

            if options.shift_owner:
                new_uid = self.new_uid(uid)
                new_gid = self.new_gid(gid)

            # Symlinks cannot have ACLs.
            if options.shift_acl and not path.is_symlink():
                acl = posix1e.ACL(file=path)
                modified_acl_entries = self.shift_acl(acl, False)
                new_acl = len(modified_acl_entries) > 0

                if is_dir:
                    default_acl = posix1e.ACL(filedef=path)
                    modified_default_acl_entries = self.shift_acl(default_acl, True)
                    new_default_acl = len(modified_default_acl_entries) > 0

            if new_uid == -1 and new_gid == -1 and not new_acl and not new_default_acl:
                stats.skipped += 1
                if not options.quiet:
                    suffix = "/" if is_dir else ""
                    print(f"{path}{suffix}: {uid}:{gid} skip")
                return False

            stats.shifted_paths += 1
            if new_uid != -1:
                stats.shifted_uids += 1
            if new_gid != -1:
                stats.shifted_gids += 1
            if new_acl:
                stats.shifted_acls += len(modified_acl_entries)
            if new_default_acl:
                stats.shifted_default_acls += len(modified_default_acl_entries)

            if not options.quiet:
                suffix = "/" if is_dir else ""
                show_uid = uid if new_uid == -1 else new_uid
                show_gid = gid if new_gid == -1 else new_gid
                heading = f"{path}{suffix}:"
                n = len(heading)
                if options.shift_owner:
                    print(f"{heading} {uid}:{gid} -> {show_uid}:{show_gid}")
                    heading = n * " "
                if options.shift_acl:
                    for entry in modified_acl_entries:
                        print(f"{heading} {entry}")
                        heading = n * " "
                    for entry in modified_default_acl_entries:
                        print(f"{heading} {entry}")

            if not options.dry_run:
                if new_uid != -1 or new_gid != -1:
                    os.chown(path, new_uid, new_gid, follow_symlinks=False)
                if new_acl:
                    assert acl is not None
                    acl.applyto(path)
                if new_default_acl:
                    assert default_acl is not None
                    default_acl.applyto(path, posix1e.ACL_TYPE_DEFAULT)

            return True
        except:
            raise RuntimeError(f"Failed to shift UID/GID for: {path}")

    def run(
        self, path: str, options: ShifterOptions = ShifterOptions()
    ) -> ShifterStats:
        stats = ShifterStats()

        for root, dirs, files in os.walk(path, followlinks=False):
            if "root" == path:
                continue

            for d in dirs:
                self.shift(Path(root) / d, options, stats)

            for f in files:
                self.shift(Path(root) / f, options, stats)

        return stats
