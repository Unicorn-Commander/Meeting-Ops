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
    def test_digest_lock(self):
        self.assertEqual(set(LOCK['images']), {'parakeet-svc', 'parakeet-stream-svc',
                                              'speaker-svc', 'parakeet-openai-shim'})
        for name, image in LOCK['images'].items():
            self.assertRegex(image, '^git.unicorncommander.ai/unicorncommander/amanuensis/'
                             + re.escape(name) + r'@sha256:[0-9a-f]{64}$')

    def test_host_overrides_change_only_image_and_build(self):
        cases = [('bigboy', {'meet-speaker-svc': 'speaker-svc'}),
                 ('midboy1', {'parakeet': 'parakeet-svc', 'parakeet-stream': 'parakeet-stream-svc'}),
                 ('midboy2', {'speaker-svc': 'speaker-svc'}),
                 ('amanuensis/shim', {'parakeet-openai-shim': 'parakeet-openai-shim'})]
        for folder, mapping in cases:
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as td:
                base = Path(td) / 'base.json'
                services = {name: {'image': 'old:test', 'build': '.',
                    'environment': {'SYNTHETIC_SENTINEL': 'preserve'},
                    'volumes': ['./patches/main.py:/app/main.py:ro'],
                    'ports': ['127.0.0.1:18000:8881'],
                    'deploy': {'resources': {'reservations': {'devices': [
                        {'driver': 'nvidia', 'device_ids': ['synthetic-gpu'], 'capabilities': ['gpu']} ]}}}}
                    for name in mapping}
                services['unrelated-voice'] = {'image': 'leave:unchanged'}
                base.write_text(json.dumps({'services': services}))
                before = compose(base)
                after = compose(base, ROOT / 'deploy' / folder / 'docker-compose.amanuensis.yml')
                expected = json.loads(json.dumps(before))
                for name, svc in mapping.items():
                    expected['services'][name]['image'] = LOCK['images'][svc]
                    expected['services'][name].pop('build')
                # Compose generates its project name from each temporary directory.
                after.pop('name', None); expected.pop('name', None)
                # Network names likewise follow that synthetic project name.
                for doc in (after, expected):
                    for net in doc.get('networks', {}).values():
                        net.pop('name', None)
                self.assertEqual(after, expected)

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
