"""Compose-only contracts. No daemon, GPU, environment file or live service needed."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'deploy/amanuensis/images.lock.json').read_text())


def compose(*paths, profiles=False):
    # Never interpolate an operator's environment or implicit .env during tests.
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'DOCKER_CONFIG')}
    with tempfile.TemporaryDirectory() as empty:
        args = ['docker', 'compose', '--env-file', '/dev/null', '--project-directory', str(Path(paths[0]).parent)]
        for path in paths:
            args.extend(['-f', str(path)])
        if profiles:
            args.extend(['--profile', 'bundled-engine'])
        result = subprocess.run(args + ['config', '--format', 'json'], env=env,
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)


class ImageContract(unittest.TestCase):
    def test_commit_tag_lock(self):
        self.assertEqual(set(LOCK['images']), {'parakeet-svc', 'parakeet-stream-svc',
                                              'speaker-svc', 'parakeet-openai-shim'})
        for name, image in LOCK['images'].items():
            self.assertRegex(image, '^git.unicorncommander.ai/unicorncommander/amanuensis/'
                             + re.escape(name) + ':' + LOCK['engine_revision'] + '$')

    def test_host_overrides_preserve_live_contract(self):
        cases = [('bigboy', {'meet-speaker-svc': 'speaker-svc'}),
                 ('midboy1', {'parakeet': 'parakeet-svc', 'parakeet-stream': 'parakeet-stream-svc'}),
                 ('midboy2', {'speaker-svc': 'speaker-svc'}),
                 ('amanuensis/shim', {'parakeet-openai-shim': 'parakeet-openai-shim'})]
        for folder, mapping in cases:
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as td:
                base = Path(td) / 'base.json'
                services = {name: {'image': 'old:test', 'build': '.',
                    'environment': {'SYNTHETIC_SENTINEL': 'preserve'},
                    'volumes': (['parakeet_models:/models', './patches/main.py:/app/main.py:ro'] if name == 'parakeet' else
                                ['/home/muut/speaker-models:/models', './patches/main.py:/app/main.py:ro'] if name == 'speaker-svc' else
                                ['cache:/models']),
                    'ports': ['127.0.0.1:18000:8881'],
                    'deploy': {'resources': {'reservations': {'devices': [
                        {'driver': 'nvidia', 'device_ids': ['synthetic-gpu'], 'capabilities': ['gpu']} ]}}}}
                    for name in mapping}
                services['unrelated-voice'] = {'image': 'leave:unchanged'}
                base.write_text(json.dumps({'services': services, 'volumes': {'parakeet_models': {}, 'cache': {}}}))
                before = compose(base)
                after = compose(base, ROOT / 'deploy' / folder / 'docker-compose.amanuensis.yml')
                expected = json.loads(json.dumps(before))
                for name, svc in mapping.items():
                    expected['services'][name]['image'] = LOCK['images'][svc]
                    expected['services'][name].pop('build')
                    if name in ('parakeet', 'speaker-svc'):
                        expected['services'][name]['volumes'] = [m for m in expected['services'][name]['volumes']
                                                                 if m['target'] != '/app/main.py']
                    if name == 'parakeet':
                        expected['services'][name]['environment']['PARAKEET_MODEL_PRECISION'] = 'fp32'
                # Compose generates its project name from each temporary directory.
                after.pop('name', None); expected.pop('name', None)
                # Network names likewise follow that synthetic project name.
                for doc in (after, expected):
                    for net in doc.get('networks', {}).values():
                        net.pop('name', None)
                self.assertEqual(after, expected)

    def test_no_host_main_mount_and_explicit_fp32(self):
        for path in (ROOT / 'deploy').rglob('docker-compose.amanuensis.yml'):
            self.assertNotRegex(path.read_text(), r'(?m)^\s*-.*main\.py')
            self.assertNotIn('/app/main.py', path.read_text())
        text = (ROOT / 'deploy/midboy1/docker-compose.amanuensis.yml').read_text()
        self.assertRegex(text, r'PARAKEET_MODEL_PRECISION:\s+fp32')
        self.assertEqual(LOCK['engine_revision'], '76a90de7fccfa3bf38e054711107e02e3656c0e1')
        self.assertEqual(LOCK['build_run'], 2538)

    def test_bundle_is_opt_in(self):
        doc = compose(ROOT / 'deploy/bundled-engine/docker-compose.yml')
        self.assertEqual(doc['services'], {})

    def test_bundle_images_and_isolation(self):
        doc = compose(ROOT / 'deploy/bundled-engine/docker-compose.yml', profiles=True)
        self.assertEqual(set(doc['services']), set(LOCK['images']))
        for name, svc in doc['services'].items():
            self.assertEqual(svc['image'], LOCK['images'][name])
            for prohibited in ('build', 'ports', 'devices', 'privileged', 'runtime', 'deploy'):
                self.assertNotIn(prohibited, svc)
            self.assertEqual(svc['restart'], 'no')
            self.assertIn('amanuensis-local', svc['networks'])

    def test_bundled_caller_dns_and_port_contract(self):
        doc = compose(ROOT / 'docker-compose.dev.yml',
                      ROOT / 'deploy/bundled-engine/docker-compose.yml',
                      ROOT / 'deploy/bundled-engine/docker-compose.callers.yml', profiles=True)
        backend = doc['services']['backend']
        self.assertIn('unicorn-network', backend['networks'])
        self.assertIn('amanuensis-local', backend['networks'])
        for key, target in [('PARAKEET_SERVER_URL', 'parakeet-svc:8881'),
                            ('PARAKEET_STREAM_URL', 'parakeet-stream-svc:8895'),
                            ('SPEAKER_SVC_URL', 'speaker-svc:8889')]:
            self.assertEqual(backend['environment'][key], 'http://' + target)
        self.assertEqual(doc['services']['parakeet-openai-shim']['environment']['PARAKEET_URL'],
                         'http://parakeet-svc:8881')


if __name__ == '__main__':
    unittest.main(verbosity=2)
