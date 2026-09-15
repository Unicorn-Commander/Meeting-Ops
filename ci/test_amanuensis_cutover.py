"""Offline failure-path tests. Never SSH, pull, or run the cutover entrypoint."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cutover', ROOT / 'deploy/cutover/amanuensis_images.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CutoverContract(unittest.TestCase):
    def test_order(self):
        self.assertEqual([(r[0], r[1]) for r in c.SERVICES], [
            ('midboy2', 'speaker-svc'), ('midboy1', 'parakeet'),
            ('midboy1', 'parakeet-openai-shim'), ('midboy1', 'parakeet-stream')])

    def test_session_gate_fails_closed(self):
        self.assertTrue(c.zero_sessions({'count': 0, 'active_sessions': []}))
        for response in ({}, {'count': False, 'active_sessions': []},
                         {'count': 0}, {'count': 0, 'active_sessions': [{}]},
                         {'count': 1, 'active_sessions': [{}]}):
            self.assertFalse(c.zero_sessions(response))

    def test_health_requires_models_and_real_booleans(self):
        for service in ('parakeet', 'parakeet-stream'):
            self.assertFalse(c.healthy(service, {'status': 'ok'}))
            self.assertFalse(c.healthy(service, {'status': 'ok', 'model_loaded': 'true'}))
            self.assertTrue(c.healthy(service, {'status': 'ok', 'model_loaded': True}))
        self.assertFalse(c.healthy('speaker-svc', {'status': 'ok', 'embedder_loaded': True}))
        self.assertTrue(c.healthy('speaker-svc', {'status': 'ok', 'embedder_loaded': True,
                                               'diarizer_available': True, 'diarizer_error': None}))
        self.assertTrue(c.healthy('parakeet-openai-shim', {'status': 'ok', 'ok': True}))

    def test_log_and_socket_checks(self):
        from subprocess import CompletedProcess
        with patch.object(c, 'http', return_value={'count': 0, 'active_sessions': []}), \
             patch.object(c, 'command', return_value=''), \
             patch.object(c.subprocess, 'run', return_value=CompletedProcess([], 0, '', '/transcribe duration=2')):
            with self.assertRaises(c.GateError):
                c.quiet('midboy1')
        with patch.object(c, 'command', return_value='0 0 127.0.0.1:8889 10.0.0.1:32123'), \
             patch.object(c.subprocess, 'run', return_value=CompletedProcess([], 0, '', '')):
            with self.assertRaises(c.GateError):
                c.quiet('midboy2')

    def test_parity_rejects_mount_env_and_gpu_drift(self):
        old = {'services': {'speaker-svc': {'image': 'old', 'environment': {
            'SPEAKER_GPU_ACQUIRE_TIMEOUT': '1500', 'CHUNK_WINDOW_SECONDS': '3600'},
            'volumes': [{'target': '/models', 'source': '/home/muut/speaker-models'},
                        {'target': '/app/main.py', 'source': '/patch/main.py'}],
            'deploy': {'gpu': 'original-uuid'}}}}
        after = copy.deepcopy(old)
        after['services']['speaker-svc']['image'] = 'new'
        after['services']['speaker-svc']['volumes'].pop()
        c.allowed_merge(old, after, {'speaker-svc': 'speaker-svc'}, {'speaker-svc': 'new'})
        for key, value in [('environment', {}), ('volumes', []), ('deploy', {'gpu': 'other'})]:
            drift = copy.deepcopy(after)
            drift['services']['speaker-svc'][key] = value
            with self.assertRaises(c.GateError):
                c.allowed_merge(old, drift, {'speaker-svc': 'speaker-svc'}, {'speaker-svc': 'new'})

    def transaction(self, failure=None, rollback_failure=False):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        saved = root / 'parakeet'
        saved.mkdir()
        args = ['docker', 'compose', '--project-directory', '/live', '-p', 'midboy1', '-f', '/live/base.yml']
        old = {'Id': 'container-old', 'Image': 'sha256:old', 'Config': {'Env': []}}
        before = {'services': {'parakeet': {'image': 'old'}}}
        record = {'status': 'PREFLIGHT', 'container_id': old['Id'], 'image_id': old['Image'],
                  'new_image_id': 'sha256:new', 'compose_args': args, 'service_override': '/tmp/reviewed.yml',
                  'repo_digest': 'registry/image@sha256:new'}
        c.write_json(saved / 'record.json', record)
        c.write_json(saved / 'before.json', before)
        c.write_json(saved / 'after.json', before)
        calls = []
        def command(argv, **kwargs):
            calls.append(argv)
            if 'config' in argv:
                return json.dumps(before)
            if argv[:3] == ['docker', 'image', 'inspect']:
                return '[{"Id":"sha256:new"}]'
            if 'up' in argv and failure == 'recreate':
                raise c.GateError('injected recreation failure')
            return ''
        def fails_at(point):
            def fn(*a, **kw):
                if failure == point:
                    raise c.GateError('injected ' + point)
            return fn
        with patch.object(c, 'wait_quiet'), patch.object(c, 'inspect', return_value=old), \
             patch.object(c, 'compose_context', return_value=(args, [])), \
             patch.object(c, 'command', side_effect=command), \
             patch.object(c, 'verify_runtime', side_effect=fails_at('runtime')), \
             patch.object(c, 'wait_health', side_effect=fails_at('health')), \
             patch.object(c, 'probe', side_effect=fails_at('probe')), \
             patch.object(c, 'rollback', side_effect=c.GateError('rollback failed') if rollback_failure else None) as rb:
            result = c.cutover({'service': 'parakeet', 'pins': {'parakeet-svc': 'new'},
                                'health_timeout': 1, 'probe_timeout': 1, 'run': 'abc'}, root)
        return result, rb, calls

    def test_success_recreates_only_target(self):
        result, rb, calls = self.transaction()
        self.assertEqual(result['status'], 'PASS')
        rb.assert_not_called()
        up = next(x for x in calls if 'up' in x)
        self.assertEqual(up[-1], 'parakeet')
        for flag in ('--no-deps', '--no-build', '--force-recreate'):
            self.assertIn(flag, up)
        self.assertEqual(up[up.index('--pull') + 1], 'never')

    def test_any_recreation_readiness_or_probe_failure_rolls_back(self):
        for failure in ('recreate', 'runtime', 'health', 'probe'):
            with self.subTest(failure=failure):
                result, rb, _ = self.transaction(failure)
                self.assertEqual(result['status'], 'ROLLED_BACK')
                rb.assert_called_once()
        result, rb, _ = self.transaction('probe', rollback_failure=True)
        self.assertEqual(result['status'], 'ROLLBACK_FAILED')

    def test_rollback_restores_frozen_image_mount_and_literal_environment(self):
        with tempfile.TemporaryDirectory() as td:
            saved = Path(td)
            env = {'LITERAL': '$not_an_environment_reference'}
            mounts = [{'Type': 'bind', 'Source': '/live/patch/main.py', 'Destination': '/app/main.py', 'RW': False}]
            before = {'services': {'parakeet': {'image': 'mutable:old', 'build': '.',
                'environment': env, 'volumes': ['/live/patch/main.py:/app/main.py:ro']}}}
            old = {'Image': 'sha256:old', 'Mounts': mounts, 'Config': {'Env': ['LITERAL=$not_an_environment_reference']},
                   'HostConfig': {'DeviceRequests': None, 'Runtime': 'nvidia'}}
            c.write_json(saved / 'before.json', before)
            c.write_json(saved / 'inspect.json', old)
            record = {'image_id': 'sha256:old', 'compose_args': [
                'docker', 'compose', '--project-directory', '/live', '-p', 'midboy1', '-f', '/live/base.yml']}
            with patch.object(c, 'command') as cmd, patch.object(c, 'inspect', return_value=old), \
                 patch.object(c, 'wait_health'):
                c.rollback(saved, record, 'parakeet', 'meet-parakeet-svc', 8881, 1)
            frozen = json.loads((saved / 'rollback.compose.json').read_text())['services']['parakeet']
            self.assertEqual(frozen['image'], 'sha256:old')
            self.assertNotIn('build', frozen)
            self.assertEqual(frozen['environment']['LITERAL'], '$$not_an_environment_reference')
            self.assertEqual(frozen['volumes'], before['services']['parakeet']['volumes'])
            argv = cmd.call_args.args[0]
            self.assertEqual(argv[argv.index('-p') + 1], 'midboy1')
            self.assertEqual(argv[-1], 'parakeet')

    def run_controller(self, dry_run):
        from subprocess import CompletedProcess
        import base64
        import io
        argv = ['cutover', '--dry-run'] if dry_run else ['cutover', '--approved-by', 'Aaron', '--traffic-drained']
        calls = []
        def remote(argv, **kwargs):
            request = json.loads(base64.b64decode(argv[-1].split()[-1]))
            calls.append(request)
            def receipt(service, status):
                return {'service': service, 'status': status, 'digest': 'digest', 'record': '/tmp/private'}
            if request['mode'] == 'preflight':
                result = [receipt(r[1], 'PREFLIGHT') for r in c.SERVICES if r[0] == request['host']]
            else:
                result = receipt(request['service'], 'ROLLED_BACK')
            return CompletedProcess(argv, 0, json.dumps(result), '')
        with patch.object(c.sys, 'argv', argv), patch.object(c.sys, 'stdout', io.StringIO()), \
             patch.object(c.subprocess, 'run', side_effect=remote):
            if dry_run:
                c.main()
            else:
                with self.assertRaises(c.GateError):
                    c.main()
        return calls

    def test_dry_run_only_preflights_both_hosts(self):
        calls = self.run_controller(True)
        self.assertEqual([(p['host'], p['mode']) for p in calls],
                         [('midboy2', 'preflight'), ('midboy1', 'preflight')])

    def test_controller_stops_after_first_failed_service(self):
        calls = self.run_controller(False)
        self.assertEqual([p['service'] for p in calls if p['mode'] == 'cutover'], ['speaker-svc'])

    def test_probe_rejects_false_success(self):
        with patch.object(c, 'http', return_value={'status': 'degraded'}):
            for service, port in [('speaker-svc', 8889), ('parakeet', 8881),
                                  ('parakeet-stream', 8895), ('parakeet-openai-shim', 8011)]:
                with self.assertRaises(c.GateError):
                    c.probe(service, port, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
