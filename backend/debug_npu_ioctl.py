#!/usr/bin/env python3
"""
Debug NPU IOCTL calls to understand the exact structures needed
"""
import os
import struct
import fcntl
import ctypes
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants from kernel header
DRM_COMMAND_BASE = 0x40
DRM_AMDXDNA_CREATE_BO = 3

def DRM_IOWR(cmd, size):
    return (0xC0000000 | (size << 16) | (ord('d') << 8) | cmd)

# Buffer types
AMDXDNA_BO_SHMEM = 1
AMDXDNA_BO_CMD = 4

def test_buffer_creation():
    """Test buffer object creation with different approaches"""
    try:
        fd = os.open("/dev/accel/accel0", os.O_RDWR)
        logger.info("✅ Opened NPU device")
        
        # Try different IOCTL command calculations
        ioctl_cmds = [
            # Method 1: Direct calculation
            DRM_IOWR(DRM_COMMAND_BASE + DRM_AMDXDNA_CREATE_BO, 32),
            # Method 2: Linux kernel style (different direction bits)
            0xC0206443,  # From strace output if available
            # Method 3: With write bit
            (0xC0000000 | (32 << 16) | (ord('d') << 8) | 0x43),
        ]
        
        for i, ioctl_cmd in enumerate(ioctl_cmds):
            logger.info(f"\n--- Testing IOCTL method {i+1}: 0x{ioctl_cmd:08X} ---")
            
            # Create buffer structure
            bo_data = bytearray(32)
            struct.pack_into('QQQII', bo_data, 0,
                            0,      # flags
                            0,      # vaddr
                            4096,   # size
                            AMDXDNA_BO_SHMEM,  # type
                            0)      # handle (output)
            
            try:
                fcntl.ioctl(fd, ioctl_cmd, bo_data)
                
                # Check if we got a handle
                _, _, _, _, handle = struct.unpack_from('QQQII', bo_data, 0)
                if handle != 0:
                    logger.info(f"✅ SUCCESS! Got handle: {handle}")
                    logger.info(f"   IOCTL command: 0x{ioctl_cmd:08X}")
                    return True
                else:
                    logger.warning(f"❌ No handle returned")
                    
            except OSError as e:
                logger.debug(f"❌ IOCTL failed: {e}")
                
        os.close(fd)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        
    return False

def check_ioctl_with_strace():
    """Instructions for using strace to debug"""
    logger.info("\n=== STRACE DEBUGGING ===")
    logger.info("To see the exact IOCTL calls that work, run:")
    logger.info("  sudo strace -e ioctl -x /opt/xilinx/xrt/bin/xbutil examine")
    logger.info("Look for successful ioctl calls to /dev/accel/accel0")
    logger.info("The hex number after 'ioctl(' is what we need")

if __name__ == "__main__":
    logger.info("=== NPU IOCTL Debug ===")
    
    # First check kernel module
    os.system("lsmod | grep amdxdna")
    
    # Test buffer creation
    if not test_buffer_creation():
        check_ioctl_with_strace()
        
        # Try using XRT tools if available
        logger.info("\n=== Checking XRT tools ===")
        xrt_path = "/opt/xilinx/xrt/bin/xbutil"
        if os.path.exists(xrt_path):
            logger.info("XRT tools found. Try:")
            logger.info(f"  {xrt_path} examine")
        else:
            logger.info("XRT tools not found")