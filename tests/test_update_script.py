"""Offline integration checks for failure isolation and source provenance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpdateScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'scripts', self.root / 'scripts')
        self.rules = self.root / 'rules'
        self.rules.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        for name, content in [('first', 'new.example\n'), ('a', '10.0.0.0/24\n'),
                              ('b', '10.0.0.0/25\n'), ('last', 'last.example\n')]:
            (self.inputs / name).write_text(content)
        # Stub only transport/conversion: production shell, validation and merge
        # helper are exercised. Real Mihomo conversion is a separate CI step.
        self.program('curl', '''#!/usr/bin/env python3
import os,pathlib,sys
args=sys.argv[1:]; url=next(a for a in args if a.startswith('https://'))
p=pathlib.Path(os.environ['TEST_INPUTS'])/url.rsplit('/',1)[-1]
if not p.exists(): sys.exit(22)
pathlib.Path(args[args.index('--output')+1]).write_bytes(p.read_bytes())
''')
        self.program('mihomo', '''#!/usr/bin/env python3
import pathlib,sys
args=sys.argv[1:]
if args[0]=='-v': print('Test Mihomo')
elif args[0]=='convert-ruleset': pathlib.Path(args[4]).write_bytes(pathlib.Path(args[3]).read_bytes())
elif args[0]!='-t': sys.exit(1)
''')
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        MIHOMO_BIN=str(self.bin / 'mihomo'), TEST_INPUTS=str(self.inputs),
                        GITHUB_OUTPUT=str(self.root / 'github-output'))
        common = dict(input_format='text', output_format='mrs', source_license='NOASSERTION',
                      minimum_entries=1, minimum_source_bytes=1, minimum_artifact_bytes=1)
        self.manifest = {
            'first': dict(common, behavior='domain', source_url='https://fixture/first'),
            'china_ip': dict(common, behavior='ipcidr', max_address_change_fraction=0.01,
                             sources=[dict(url='https://fixture/' + n, minimum_entries=1,
                                           minimum_source_bytes=1, source_license='NOASSERTION')
                                      for n in ['a', 'b']]),
            'last': dict(common, behavior='domain', source_url='https://fixture/last')}
        baseline = b'10.0.0.0/24\n'
        (self.rules / 'china_ip.mrs').write_bytes(baseline)
        (self.rules / 'china_ip.json').write_text(json.dumps(dict(
            artifact_sha256=hashlib.sha256(baseline).hexdigest())))
        (self.rules / 'first.mrs').write_text('old.example\n')
        (self.rules / 'SHA256SUMS').write_text('previous checksums\n')

    def program(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.rules.iterdir()}

    def run_update(self):
        (self.root / 'sources.json').write_text(json.dumps(self.manifest))
        return subprocess.run(['bash', str(self.root / 'scripts/update-rulesets.sh')],
                              env=self.env, text=True, capture_output=True)

    def fails_without_changes(self, expected):
        before = self.snapshot()
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / 'github-output').exists())

    def test_success_provenance_and_idempotence(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        metadata = json.loads((self.rules / 'china_ip.json').read_text())
        self.assertEqual(len(metadata['sources']), 2)
        self.assertEqual(metadata['sources'][0]['source_sha256'],
                         hashlib.sha256((self.inputs / 'a').read_bytes()).hexdigest())
        self.assertEqual(metadata['coverage']['added_ipv4_addresses'], 0)
        before = self.snapshot()
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('changed=false rulesets=3', result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_missing_each_required_source(self):
        for name in ['a', 'b']:
            with self.subTest(name=name):
                path = self.inputs / name
                data = path.read_bytes()
                path.unlink()
                self.fails_without_changes('https://fixture/' + name)
                path.write_bytes(data)

    def test_invalid_empty_and_ipv6(self):
        for text in ['# empty\n', '<html>failure</html>\n', '2001:db8::/32\n']:
            with self.subTest(text=text):
                (self.inputs / 'b').write_text(text)
                self.fails_without_changes('https://fixture/b')

    def test_per_source_floor(self):
        self.manifest['china_ip']['sources'][0]['minimum_entries'] = 2
        self.fails_without_changes('below safety minimum')

    def test_per_source_byte_floor(self):
        self.manifest['china_ip']['sources'][0]['minimum_source_bytes'] = 100
        self.fails_without_changes('below safety minimum')

    def test_merged_floor(self):
        self.manifest['china_ip']['minimum_entries'] = 3
        self.fails_without_changes('too few entries')

    def test_large_addition(self):
        (self.inputs / 'b').write_text('10.0.1.0/24\n')
        self.fails_without_changes('manual source review required')

    def test_large_removal(self):
        (self.inputs / 'a').write_text('10.0.0.0/25\n')
        self.fails_without_changes('manual source review required')

    def test_corrupt_baseline(self):
        (self.rules / 'china_ip.mrs').write_text('10.0.0.0/23\n')
        self.fails_without_changes('checksum mismatch')

    def test_missing_baseline(self):
        (self.rules / 'china_ip.mrs').unlink()
        self.fails_without_changes('china_ip.mrs')

    def test_later_failure_preserves_earlier_rulesets(self):
        (self.inputs / 'last').unlink()
        self.fails_without_changes('https://fixture/last')

    def test_manifest_rejects_ambiguous_sources(self):
        self.manifest['china_ip']['source_url'] = 'https://fixture/a'
        self.fails_without_changes('')

    def test_manifest_rejects_unsafe_aggregate_minimum_numbers(self):
        for field in ['minimum_entries', 'minimum_source_bytes', 'minimum_artifact_bytes']:
            for value in [1000000.5, 1e30, 2**63]:
                with self.subTest(field=field, value=value):
                    original = self.manifest['first'][field]
                    try:
                        self.manifest['first'][field] = value
                        self.fails_without_changes('')
                    finally:
                        self.manifest['first'][field] = original

    def test_manifest_rejects_unsafe_per_source_minimum_numbers(self):
        source = self.manifest['china_ip']['sources'][0]
        for field in ['minimum_entries', 'minimum_source_bytes']:
            for value in [1.5, 1e30, 2**63]:
                with self.subTest(field=field, value=value):
                    original = source[field]
                    try:
                        source[field] = value
                        self.fails_without_changes('')
                    finally:
                        source[field] = original


if __name__ == '__main__':
    unittest.main()
