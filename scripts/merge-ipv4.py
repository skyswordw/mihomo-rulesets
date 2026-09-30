#!/usr/bin/env python3
"""Validate required IPv4 sources, preserve their union, and guard coverage drift."""

import argparse
import hashlib
import ipaddress
import json
import pathlib
import sys
from decimal import Decimal, InvalidOperation


def _entries(text, label):
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        try:
            ipaddress.IPv4Network(entry, strict=False)
        except ValueError as exc:
            raise ValueError(f"{label}:{number}: invalid IPv4 entry: {entry}") from exc
        entries.append(entry)
    if not entries:
        raise ValueError(f"{label}: source contains no IPv4 entries")
    return entries


def parse_ipv4(path):
    return _entries(path.read_text(encoding="utf-8"), str(path))


def merge_ipv4(paths):
    entries = set()
    for path in paths:
        entries.update(parse_ipv4(path))
    if not entries:
        raise ValueError("No IPv4 sources supplied")
    # Preserve the old merger's exact-entry union and lexical order. Do not
    # collapse, filter or silently substitute sources.
    return "".join(entry + "\n" for entry in sorted(entries))


def _intervals(text, label):
    networks = [ipaddress.IPv4Network(s, strict=False) for s in _entries(text, label)]
    return [(int(n.network_address), int(n.broadcast_address))
            for n in ipaddress.collapse_addresses(networks)]


def coverage(previous_text, current_text, max_change_fraction=0.01):
    try:
        limit = Decimal(str(max_change_fraction))
    except InvalidOperation as exc:
        raise ValueError("Coverage change fraction must be a number") from exc
    if not limit.is_finite() or not 0 <= limit <= 1:
        raise ValueError("Coverage change fraction must be between 0 and 1")
    previous = _intervals(previous_text, "previous")
    current = _intervals(current_text, "current")
    old_count = sum(end - start + 1 for start, end in previous)
    new_count = sum(end - start + 1 for start, end in current)
    common = i = j = 0
    while i < len(previous) and j < len(current):
        start = max(previous[i][0], current[j][0])
        end = min(previous[i][1], current[j][1])
        common += max(0, end - start + 1)
        if previous[i][1] < current[j][1]:
            i += 1
        else:
            j += 1
    added, removed = new_count - common, old_count - common
    result = dict(previous_ipv4_addresses=old_count, current_ipv4_addresses=new_count,
                  added_ipv4_addresses=added, removed_ipv4_addresses=removed)
    if added > old_count * limit or removed > old_count * limit:
        raise ValueError(f"IPv4 coverage change exceeds {limit * 100}% of previous "
                         f"{old_count} addresses: added={added}, removed={removed}; "
                         "manual source review required (no automatic fallback)")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    merge = sub.add_parser("merge")
    merge.add_argument("--sources-json", required=True)
    merge.add_argument("--metadata", type=pathlib.Path, required=True)
    merge.add_argument("paths", nargs="+", type=pathlib.Path)
    check = sub.add_parser("coverage")
    check.add_argument("--previous", type=pathlib.Path, required=True)
    check.add_argument("--current", type=pathlib.Path, required=True)
    check.add_argument("--max-change-fraction", default="0.01")
    args = parser.parse_args()
    if args.command == "coverage":
        print(json.dumps(coverage(args.previous.read_text(), args.current.read_text(),
                                  args.max_change_fraction)))
        return
    sources = json.loads(args.sources_json)
    if len(sources) != len(args.paths):
        raise ValueError("Every declared source must be supplied")
    metadata = []
    for source, path in zip(sources, args.paths):
        try:
            entries = parse_ipv4(path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{source['url']}: {exc}") from exc
        data = path.read_bytes()
        if len(entries) < source["minimum_entries"] or len(data) < source["minimum_source_bytes"]:
            raise ValueError(f"{source['url']}: source below safety minimum: "
                             f"entries={len(entries)}, bytes={len(data)}")
        metadata.append(dict(source_url=source["url"], source_sha256=hashlib.sha256(data).hexdigest(),
                             source_entries=len(entries), source_bytes=len(data),
                             source_license=source["source_license"]))
    merged = merge_ipv4(args.paths)
    args.metadata.write_text(json.dumps(metadata, indent=2) + "\n")
    sys.stdout.write(merged)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(str(exc))
