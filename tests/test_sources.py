"""Offline regression tests for the required-source IPv4 merge and coverage guard."""

import importlib.util
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "merge-ipv4.py"
SPEC = importlib.util.spec_from_file_location("merge_ipv4", SCRIPT)
merge_ipv4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(merge_ipv4)


def host_entries(count, start="192.0.2.0"):
    """Build an exact, easily audited address-count fixture."""
    first = int(ipaddress.IPv4Address(start))
    return "".join(
        f"{ipaddress.IPv4Address(first + offset)}/32\n" for offset in range(count)
    )


class SourceFilesTestCase(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)

    def source(self, name, text):
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path


class ParseIPv4Tests(SourceFilesTestCase):
    def test_ignores_blank_lines_and_indented_comments(self):
        source = self.source(
            "comments.txt",
            "\n  # Source comment\n\t\n  10.0.0.0/24  \n\t192.0.2.1/32\t\n",
        )
        self.assertEqual(
            merge_ipv4.parse_ipv4(source), ["10.0.0.0/24", "192.0.2.1/32"]
        )

    def test_preserves_valid_host_bits_and_original_entry_order(self):
        source = self.source(
            "host-bits.txt", "192.0.2.123/24\n10.0.0.1/8\n192.0.2.123/24\n"
        )
        self.assertEqual(
            merge_ipv4.parse_ipv4(source),
            ["192.0.2.123/24", "10.0.0.1/8", "192.0.2.123/24"],
        )

    def test_accepts_ipv4_address_boundaries(self):
        source = self.source("boundaries.txt", "0.0.0.0/0\n255.255.255.255/32\n")
        self.assertEqual(
            merge_ipv4.parse_ipv4(source), ["0.0.0.0/0", "255.255.255.255/32"]
        )

    def test_rejects_invalid_entries_even_after_a_valid_entry(self):
        for entry in (
            "not-a-network",
            "256.1.2.3/24",
            "192.0.2.0/33",
            "192.0.2.0/-1",
            "192.0.2",
            "192.000.2.0/24",
            "192.0.2.0/24 # trailing comment",
            "192.0.2.0/24,198.51.100.0/24",
        ):
            with self.subTest(entry=entry):
                source = self.source("invalid.txt", f"10.0.0.0/24\n{entry}\n")
                with self.assertRaises(ValueError):
                    merge_ipv4.parse_ipv4(source)

    def test_rejects_ipv6_and_ipv4_mapped_ipv6(self):
        for entry in ("2001:db8::/32", "::1", "::ffff:192.0.2.1/128"):
            with self.subTest(entry=entry):
                source = self.source("ipv6.txt", f"{entry}\n")
                with self.assertRaises(ValueError):
                    merge_ipv4.parse_ipv4(source)

    def test_missing_source_is_an_error(self):
        with self.assertRaises(OSError):
            merge_ipv4.parse_ipv4(self.directory / "missing.txt")


class MergeIPv4Tests(SourceFilesTestCase):
    def test_exact_union_is_deduplicated_and_sorted_lexically(self):
        sources = [
            self.source("first.txt", "2.0.0.0/8\n10.0.0.0/8\n10.0.0.0/8\n"),
            self.source("second.txt", "192.0.2.0/24\n10.0.0.0/8\n"),
            self.source("third.txt", "198.51.100.0/24\n2.0.0.0/8\n"),
        ]
        self.assertEqual(
            merge_ipv4.merge_ipv4(sources),
            "10.0.0.0/8\n192.0.2.0/24\n198.51.100.0/24\n2.0.0.0/8\n",
        )

    def test_source_order_does_not_change_output(self):
        sources = [
            self.source("first.txt", "203.0.113.0/24\n"),
            self.source("second.txt", "10.0.0.0/8\n203.0.113.0/24\n"),
        ]
        self.assertEqual(
            merge_ipv4.merge_ipv4(sources), merge_ipv4.merge_ipv4(sources[::-1])
        )

    def test_merge_strips_whitespace_and_comments(self):
        source = self.source(
            "comments.txt", "# header\n\n 192.0.2.0/24 \n\t# comment\n\t192.0.2.0/24\t\n"
        )
        self.assertEqual(merge_ipv4.merge_ipv4([source]), "192.0.2.0/24\n")

    def test_does_not_collapse_or_normalize_distinct_entries(self):
        source = self.source(
            "overlaps.txt", "192.0.2.0/24\n192.0.2.0/25\n192.0.2.123/24\n"
        )
        self.assertEqual(
            merge_ipv4.merge_ipv4([source]),
            "192.0.2.0/24\n192.0.2.0/25\n192.0.2.123/24\n",
        )

    def test_duplicate_only_source_is_still_valid(self):
        sources = [
            self.source("first.txt", "192.0.2.0/24\n"),
            self.source("second.txt", "192.0.2.0/24\n"),
        ]
        self.assertEqual(merge_ipv4.merge_ipv4(sources), "192.0.2.0/24\n")

    def test_no_sources_is_an_error(self):
        with self.assertRaises(ValueError):
            merge_ipv4.merge_ipv4([])

    def test_every_source_must_exist(self):
        good = self.source("good.txt", "192.0.2.0/24\n")
        missing = self.directory / "missing.txt"
        for sources in ([missing, good], [good, missing], [good, missing, good]):
            with self.subTest(sources=sources):
                with self.assertRaises(OSError):
                    merge_ipv4.merge_ipv4(sources)

    def test_every_source_must_be_nonempty(self):
        good = self.source("good.txt", "192.0.2.0/24\n")
        for content in ("", "\n \t\n", "# header only\n  # no entries\n"):
            empty = self.source("empty.txt", content)
            for sources in ([empty, good], [good, empty], [good, empty, good]):
                with self.subTest(content=content, sources=sources):
                    with self.assertRaises(ValueError):
                        merge_ipv4.merge_ipv4(sources)

    def test_invalid_or_ipv6_source_is_not_silently_dropped(self):
        good = self.source("good.txt", "192.0.2.0/24\n")
        for entry in ("invalid", "2001:db8::/32"):
            bad = self.source("bad.txt", f"198.51.100.0/24\n{entry}\n")
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    merge_ipv4.merge_ipv4([good, bad, good])


class CoverageTests(unittest.TestCase):
    def assert_counts(self, previous, current, added, removed, result):
        self.assertEqual(
            result,
            {
                "previous_ipv4_addresses": previous,
                "current_ipv4_addresses": current,
                "added_ipv4_addresses": added,
                "removed_ipv4_addresses": removed,
            },
        )

    def test_identical_sets_are_stable(self):
        text = "10.0.0.0/8\n192.0.2.0/24\n"
        self.assert_counts(2**24 + 256, 2**24 + 256, 0, 0, merge_ipv4.coverage(text, text))

    def test_duplicates_and_overlapping_ranges_count_once(self):
        previous = "192.0.2.0/24\n192.0.2.0/25\n192.0.2.64/26\n192.0.2.0/24\n"
        current = "192.0.2.0/24\n192.0.2.255/32\n"
        self.assert_counts(256, 256, 0, 0, merge_ipv4.coverage(previous, current))

    def test_prefix_reorganization_without_address_changes_is_stable(self):
        self.assert_counts(
            256,
            256,
            0,
            0,
            merge_ipv4.coverage("192.0.2.0/24\n", "192.0.2.0/25\n192.0.2.128/25\n"),
        )

    def test_host_bits_are_normalized_for_coverage_only(self):
        self.assert_counts(
            256, 256, 0, 0, merge_ipv4.coverage("192.0.2.123/24\n", "192.0.2.0/24\n")
        )

    def test_coverage_ignores_comments_and_whitespace(self):
        self.assert_counts(
            256,
            256,
            0,
            0,
            merge_ipv4.coverage("# old\n 192.0.2.0/24 \n", "\n\t# new\n192.0.2.0/24\n"),
        )

    def test_counts_additions_and_removals_in_overlapping_ranges(self):
        result = merge_ipv4.coverage(
            "192.0.2.0/25\n192.0.2.0/26\n",
            "192.0.2.64/26\n192.0.2.128/26\n192.0.2.64/27\n",
            max_change_fraction=0.5,
        )
        self.assert_counts(128, 128, 64, 64, result)

    def test_equal_to_one_percent_added_is_allowed(self):
        self.assert_counts(100, 101, 1, 0, merge_ipv4.coverage(host_entries(100), host_entries(101)))

    def test_equal_to_one_percent_removed_is_allowed(self):
        self.assert_counts(100, 99, 0, 1, merge_ipv4.coverage(host_entries(100), host_entries(99)))

    def test_more_than_one_percent_added_is_rejected(self):
        with self.assertRaises(ValueError):
            merge_ipv4.coverage(host_entries(100), host_entries(102))

    def test_more_than_one_percent_removed_is_rejected(self):
        with self.assertRaises(ValueError):
            merge_ipv4.coverage(host_entries(100), host_entries(98))

    def test_equal_total_size_does_not_hide_address_churn(self):
        with self.assertRaises(ValueError):
            merge_ipv4.coverage(host_entries(100), host_entries(100, start="192.0.2.2"))

    def test_unchanged_prefix_count_does_not_hide_large_addition(self):
        with self.assertRaises(ValueError):
            merge_ipv4.coverage("192.0.2.0/24\n", "192.0.2.0/23\n")

    def test_unchanged_prefix_count_does_not_hide_large_removal(self):
        with self.assertRaises(ValueError):
            merge_ipv4.coverage("192.0.2.0/24\n", "192.0.2.0/25\n")

    def test_zero_threshold_allows_only_identical_coverage(self):
        self.assert_counts(
            100, 100, 0, 0,
            merge_ipv4.coverage(host_entries(100), host_entries(100), max_change_fraction=0),
        )
        with self.assertRaises(ValueError):
            merge_ipv4.coverage(host_entries(100), host_entries(101), max_change_fraction=0)

    def test_entire_ipv4_space_counts_correctly_without_expanding_hosts(self):
        self.assert_counts(
            2**32,
            2**32,
            0,
            0,
            merge_ipv4.coverage("0.0.0.0/0\n", "0.0.0.0/1\n128.0.0.0/1\n"),
        )

    def test_empty_previous_coverage_is_rejected(self):
        for previous in ("", "\n \t\n", "# no previous entries\n"):
            with self.subTest(previous=previous):
                with self.assertRaises(ValueError):
                    merge_ipv4.coverage(previous, "192.0.2.0/24\n")

    def test_invalid_and_ipv6_entries_are_rejected_in_either_input(self):
        good = "192.0.2.0/24\n"
        for entry in ("invalid", "256.0.0.0/24", "192.0.2.0/33", "2001:db8::/32"):
            bad = good + entry + "\n"
            for previous, current in ((bad, good), (good, bad)):
                with self.subTest(entry=entry, previous=previous, current=current):
                    with self.assertRaises(ValueError):
                        merge_ipv4.coverage(previous, current)


class CommandLineTests(SourceFilesTestCase):
    def run_helper(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *(str(argument) for argument in arguments)],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def source_config(self, name, minimum_entries=1, minimum_source_bytes=1):
        return {
            "url": f"https://example.invalid/{name}",
            "source_license": "NOASSERTION",
            "minimum_entries": minimum_entries,
            "minimum_source_bytes": minimum_source_bytes,
        }

    def test_merge_cli_writes_exact_union_and_per_source_provenance(self):
        first = self.source("first.txt", "# Header\n192.0.2.0/24\n192.0.2.0/24\n")
        second = self.source("second.txt", "198.51.100.0/24\n192.0.2.0/24\n")
        configs = [self.source_config(path.name) for path in (first, second)]
        metadata = self.directory / "metadata.json"
        result = self.run_helper(
            "merge", "--sources-json", json.dumps(configs), "--metadata", metadata, first, second
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "192.0.2.0/24\n198.51.100.0/24\n")
        expected = []
        for config, path in zip(configs, (first, second)):
            raw = path.read_bytes()
            expected.append(
                {
                    "source_url": config["url"],
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_entries": 2,
                    "source_bytes": len(raw),
                    "source_license": "NOASSERTION",
                }
            )
        self.assertEqual(json.loads(metadata.read_text(encoding="utf-8")), expected)

    def test_merge_cli_requires_every_declared_source(self):
        first = self.source("first.txt", "192.0.2.0/24\n")
        configs = [self.source_config("first.txt"), self.source_config("missing.txt")]
        metadata = self.directory / "metadata.json"
        result = self.run_helper(
            "merge", "--sources-json", json.dumps(configs), "--metadata", metadata, first
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(metadata.exists())

    def test_merge_cli_enforces_each_sources_entry_and_byte_minimum(self):
        large = self.source("large.txt", host_entries(100))
        small = self.source("small.txt", "198.51.100.0/24\n")
        for minimum_entries, minimum_bytes in ((2, 1), (1, 1000)):
            with self.subTest(minimum_entries=minimum_entries, minimum_bytes=minimum_bytes):
                configs = [
                    self.source_config("large.txt"),
                    self.source_config("small.txt", minimum_entries, minimum_bytes),
                ]
                metadata = self.directory / "metadata.json"
                result = self.run_helper(
                    "merge", "--sources-json", json.dumps(configs), "--metadata", metadata,
                    large, small,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("https://example.invalid/small.txt", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(metadata.exists())

    def test_merge_cli_missing_file_fails_without_partial_output(self):
        first = self.source("first.txt", "192.0.2.0/24\n")
        missing = self.directory / "missing.txt"
        configs = [self.source_config("first.txt"), self.source_config("missing.txt")]
        metadata = self.directory / "metadata.json"
        result = self.run_helper(
            "merge", "--sources-json", json.dumps(configs), "--metadata", metadata,
            first, missing,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("https://example.invalid/missing.txt", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(metadata.exists())

    def test_coverage_cli_returns_json_counts_at_allowed_boundary(self):
        previous = self.source("previous.txt", host_entries(100))
        current = self.source("current.txt", host_entries(101))
        result = self.run_helper("coverage", "--previous", previous, "--current", current)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "previous_ipv4_addresses": 100,
                "current_ipv4_addresses": 101,
                "added_ipv4_addresses": 1,
                "removed_ipv4_addresses": 0,
            },
        )

    def test_coverage_cli_rejects_address_loss_with_nonzero_status(self):
        previous = self.source("previous.txt", host_entries(100))
        current = self.source("current.txt", host_entries(98))
        result = self.run_helper(
            "coverage", "--previous", previous, "--current", current,
            "--max-change-fraction", "0.01",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("removed=2", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
