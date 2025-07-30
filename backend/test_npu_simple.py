#!/usr/bin/env python3
"""
Simple NPU test to verify basic functionality
"""
import os
import struct
import fcntl
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# IOCTL commands
DRM_COMMAND_BASE = 0x40
DRM_AMDXDNA_GET_INFO = 7

def DRM_IOWR(cmd, size):
    return (0x40000000 | (size << 16) | (ord('d') << 8) | cmd)

DRM_IOCTL_AMDXDNA_GET_INFO = DRM_IOWR(DRM_COMMAND_BASE + DRM_AMDXDNA_GET_INFO, 16)

def test_npu_device():
    """Test basic NPU device access"""
    try:
        # Open device
        fd = os.open("/dev/accel/accel0", os.O_RDWR)
        logger.info("✅ Opened NPU device successfully")
        
        # Try simple query - AIE version
        query_type = 2  # DRM_AMDXDNA_QUERY_AIE_VERSION
        buffer_size = 8
        buffer = bytearray(buffer_size)
        
        # Pack query structure - simpler approach
        # struct drm_amdxdna_query_info {
        #     __u32 query;      /* in */
        #     __u32 len;        /* in/out */
        #     __u64 buffer;     /* in/out */
        # };
        
        # Get buffer address
        import ctypes
        buffer_ptr = ctypes.addressof(ctypes.c_char.from_buffer(buffer))
        
        # Pack the structure
        query_data = bytearray(16)
        struct.pack_into('IIQ', query_data, 0, query_type, buffer_size, buffer_ptr)
        
        try:
            # Send IOCTL
            fcntl.ioctl(fd, DRM_IOCTL_AMDXDNA_GET_INFO, query_data)
            
            # Read version from buffer
            major, minor = struct.unpack('II', buffer)
            logger.info(f"✅ NPU AIE Version: {major}.{minor}")
            
        except OSError as e:
            logger.error(f"❌ IOCTL failed: {e}")
            logger.info("ℹ️  This might be due to:")
            logger.info("   - Incorrect IOCTL structure")
            logger.info("   - Driver expecting different parameters")
            logger.info("   - Need to check kernel headers")
        
        # Close device
        os.close(fd)
        logger.info("✅ Closed NPU device")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")

if __name__ == "__main__":
    logger.info("=== Simple NPU Test ===")
    test_npu_device()
    
    # Check if we can use the fallback transcription
    logger.info("\n=== Testing Fallback Transcription ===")
    try:
        from basic_whisper_transcriber import BasicWhisperTranscriber
        transcriber = BasicWhisperTranscriber()
        logger.info(f"✅ Fallback transcriber ready: {transcriber.model_loaded}")
        
        # Test with a simple audio file if available
        test_audio = "/tmp/recordings/session_1753333393/recording.wav"
        if os.path.exists(test_audio):
            result = transcriber.transcribe(test_audio)
            logger.info(f"✅ Transcription result: {result.get('text', '')[:100]}...")
            logger.info(f"   Duration: {result.get('duration', 0):.1f}s")
            logger.info(f"   Processing time: {result.get('processing_time', 0):.2f}s")
    except Exception as e:
        logger.error(f"❌ Fallback test failed: {e}")