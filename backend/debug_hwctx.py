#!/usr/bin/env python3
"""
Debug NPU hardware context creation
"""
import os
import struct
import fcntl
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Working IOCTL commands
DRM_IOCTL_AMDXDNA_CREATE_BO = 0xC0206443
DRM_IOCTL_AMDXDNA_CREATE_HWCTX = 0xC0386440

# Buffer types
AMDXDNA_BO_SHMEM = 1
AMDXDNA_BO_CMD = 4

def create_buffer(fd, size, bo_type):
    """Create buffer object"""
    bo_data = bytearray(32)
    struct.pack_into('QQQII', bo_data, 0, 0, 0, size, bo_type, 0)
    
    fcntl.ioctl(fd, DRM_IOCTL_AMDXDNA_CREATE_BO, bo_data)
    _, _, _, _, handle = struct.unpack_from('QQQII', bo_data, 0)
    return handle

def test_hwctx_creation():
    """Test hardware context creation"""
    try:
        fd = os.open("/dev/accel/accel0", os.O_RDWR)
        logger.info("✅ Opened NPU device")
        
        # Create required buffers
        umq_bo = create_buffer(fd, 4096, AMDXDNA_BO_CMD)
        log_bo = create_buffer(fd, 4096, AMDXDNA_BO_SHMEM)
        logger.info(f"✅ Created buffers: umq={umq_bo}, log={log_bo}")
        
        # Try different hardware context parameters
        test_params = [
            # (max_opc, num_tiles, mem_size)
            (1, 1, 4096),      # Minimal
            (4, 1, 16384),     # Small
            (16, 4, 65536),    # Medium
            (32, 4, 131072),   # Large
        ]
        
        for max_opc, num_tiles, mem_size in test_params:
            logger.info(f"\n--- Testing: max_opc={max_opc}, tiles={num_tiles}, mem={mem_size} ---")
            
            # Create hardware context structure
            hwctx_data = bytearray(56)  # Correct size
            struct.pack_into('QQQ', hwctx_data, 0,
                           0,  # ext
                           0,  # ext_flags
                           0)  # qos_p
            struct.pack_into('IIIIIIII', hwctx_data, 24,
                           umq_bo,      # umq_bo
                           log_bo,      # log_buf_bo
                           max_opc,     # max_opc
                           num_tiles,   # num_tiles
                           mem_size,    # mem_size
                           0,           # umq_doorbell (output)
                           0,           # handle (output)
                           0)           # syncobj_handle (output)
            
            try:
                fcntl.ioctl(fd, DRM_IOCTL_AMDXDNA_CREATE_HWCTX, hwctx_data)
                
                # Read outputs
                values = struct.unpack_from('IIIIIIII', hwctx_data, 24)
                handle = values[6]
                syncobj = values[7]
                
                if handle != 0:
                    logger.info(f"✅ SUCCESS! hwctx={handle}, syncobj={syncobj}")
                    logger.info(f"   Working params: max_opc={max_opc}, tiles={num_tiles}, mem={mem_size}")
                    os.close(fd)
                    return True
                else:
                    logger.warning("❌ No handle returned")
                    
            except OSError as e:
                logger.debug(f"❌ Failed: {e}")
                
        os.close(fd)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        
    return False

if __name__ == "__main__":
    logger.info("=== NPU Hardware Context Debug ===")
    
    if not test_hwctx_creation():
        logger.info("\n=== Debugging Tips ===")
        logger.info("1. Check dmesg for kernel errors: sudo dmesg | tail")
        logger.info("2. Try XRT tools: /opt/xilinx/xrt/bin/xbutil examine")
        logger.info("3. The NPU might need firmware or specific initialization")