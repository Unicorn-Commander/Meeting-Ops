
import os
import tempfile
import unittest
from npu_runtime import NPURuntime
from onnx_to_npu import WhisperNPUConverter

class TestNPURuntime(unittest.TestCase):
    def test_open_device(self):
        runtime = NPURuntime('/dev/does_not_exist')
        runtime.open_device()
        self.assertIsNone(runtime.fd, "Should not open non-existent device")
        runtime.close_device()

    def test_send_nop(self):
        runtime = NPURuntime('/dev/does_not_exist')
        runtime.open_device()
        result = runtime.send_nop()
        self.assertFalse(result, "NOP should fail if device not open")
        runtime.close_device()

    def test_load_model(self):
        runtime = NPURuntime('/dev/does_not_exist')
        runtime.load_model('fake_model.npubin')
        # No assert, just check no crash

    def test_transcribe(self):
        runtime = NPURuntime('/dev/does_not_exist')
        result = runtime.transcribe(b'fake audio')
        self.assertEqual(result, "<transcription>", "Stub should return placeholder")

class TestWhisperNPUConverter(unittest.TestCase):
    def test_onnx_to_npu_conversion(self):
        converter = WhisperNPUConverter()
        with tempfile.TemporaryDirectory() as tmpdir:
            onnx_path = os.path.join(tmpdir, 'fake.onnx')
            npu_bin_path = os.path.join(tmpdir, 'fake.npubin')
            with open(onnx_path, 'wb') as f:
                f.write(b'0' * 128)  # Dummy ONNX, printable
            converter.convert(onnx_path, npu_bin_path)
            self.assertTrue(os.path.exists(npu_bin_path), "NPU binary should be created")
            self.assertEqual(os.path.getsize(npu_bin_path), 1024, "NPU binary should be 1024 bytes (placeholder)")

if __name__ == '__main__':
    unittest.main()
