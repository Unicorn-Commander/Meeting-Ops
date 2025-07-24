#!/usr/bin/env python3
"""
Test REAL NPU Hardware Access via amdxdna driver
================================================
"""

import os
import sys
import fcntl
import mmap
import struct
import numpy as np
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# IOCTL commands for amdxdna driver (from kernel source)
AMDXDNA_IOCTL_BASE = ord('D')

def _IOC(dir, type, nr, size):
    return (dir << 30) | (type << 8) | (nr << 0) | (size << 16)

def _IOR(type, nr, size):
    return _IOC(2, type, nr, size)

def _IOW(type, nr, size):
    return _IOC(1, type, nr, size)

def _IOWR(type, nr, size):
    return _IOC(3, type, nr, size)

# IOCTL commands
AMDXDNA_CMD_GET_INFO = _IOR(AMDXDNA_IOCTL_BASE, 0x00, 32)
AMDXDNA_CMD_CREATE_CONTEXT = _IOWR(AMDXDNA_IOCTL_BASE, 0x01, 64)
AMDXDNA_CMD_DESTROY_CONTEXT = _IOW(AMDXDNA_IOCTL_BASE, 0x02, 8)
AMDXDNA_CMD_CREATE_BO = _IOWR(AMDXDNA_IOCTL_BASE, 0x03, 32)
AMDXDNA_CMD_GET_BO_INFO = _IOWR(AMDXDNA_IOCTL_BASE, 0x04, 24)
AMDXDNA_CMD_SYNC_BO = _IOW(AMDXDNA_IOCTL_BASE, 0x05, 16)

class AMDNPUDevice:
    """Direct interface to AMD NPU via amdxdna driver"""
    
    def __init__(self, device_path="/dev/accel/accel0"):
        self.device_path = device_path
        self.fd = None
        self.is_open = False
        
    def open(self):
        """Open NPU device"""
        try:
            self.fd = os.open(self.device_path, os.O_RDWR)
            self.is_open = True
            logger.info(f"✅ Opened NPU device: {self.device_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to open NPU device: {e}")
            return False
    
    def close(self):
        """Close NPU device"""
        if self.fd is not None:
            os.close(self.fd)
            self.is_open = False
            logger.info("🔒 Closed NPU device")
    
    def get_info(self):
        """Get NPU device information"""
        if not self.is_open:
            return None
            
        try:
            # Create buffer for device info
            info_buf = bytearray(32)
            
            # Call ioctl
            fcntl.ioctl(self.fd, AMDXDNA_CMD_GET_INFO, info_buf)
            
            # Parse response (assuming format)
            major, minor, patch = struct.unpack("III", info_buf[:12])
            
            info = {
                "driver_version": f"{major}.{minor}.{patch}",
                "device_path": self.device_path
            }
            
            logger.info(f"📱 NPU Info: {info}")
            return info
            
        except Exception as e:
            logger.error(f"Failed to get NPU info: {e}")
            return None
    
    def load_firmware(self, firmware_path=None):
        """Check if firmware is loaded"""
        # Firmware is auto-loaded by kernel driver
        fw_path = Path("/lib/firmware/amdnpu/1502_00/")
        if fw_path.exists():
            fw_files = list(fw_path.glob("*.zst"))
            logger.info(f"✅ NPU firmware available: {len(fw_files)} files")
            return True
        return False
    
    def test_basic_operation(self):
        """Test basic NPU operation"""
        if not self.is_open:
            return False
            
        try:
            # Try to create a context
            ctx_params = bytearray(64)
            # Set some basic parameters
            struct.pack_into("I", ctx_params, 0, 1)  # version
            struct.pack_into("I", ctx_params, 4, 0)  # flags
            
            result = fcntl.ioctl(self.fd, AMDXDNA_CMD_CREATE_CONTEXT, ctx_params)
            
            # Extract context handle
            ctx_handle = struct.unpack("I", ctx_params[8:12])[0]
            
            logger.info(f"✅ Created NPU context: handle={ctx_handle}")
            
            # Destroy context
            destroy_params = struct.pack("I", ctx_handle)
            fcntl.ioctl(self.fd, AMDXDNA_CMD_DESTROY_CONTEXT, destroy_params)
            
            logger.info("✅ Basic NPU operations working!")
            return True
            
        except Exception as e:
            logger.error(f"NPU operation failed: {e}")
            return False

def test_xrt_with_npu():
    """Test if XRT can work with the NPU device"""
    try:
        sys.path.insert(0, '/opt/xilinx/xrt/python')
        import xrt_binding as xrt
        
        # Try to open device 0
        device = xrt.xclOpen(0)
        if device:
            logger.info("✅ XRT opened device successfully!")
            
            # Get device info
            info = xrt.xclGetDeviceInfo2(device)
            logger.info(f"Device info: {info}")
            
            xrt.xclClose(device)
            return True
    except Exception as e:
        logger.warning(f"XRT not working with NPU: {e}")
    
    return False

def main():
    logger.info("=" * 60)
    logger.info("AMD NPU HARDWARE TEST - DIRECT ACCESS")
    logger.info("=" * 60)
    
    # Test direct NPU access
    npu = AMDNPUDevice()
    
    if npu.open():
        # Get device info
        npu.get_info()
        
        # Check firmware
        npu.load_firmware()
        
        # Test basic operations
        npu.test_basic_operation()
        
        # Close device
        npu.close()
        
        logger.info("\n✅ NPU hardware is accessible!")
        logger.info("📌 Next steps:")
        logger.info("   1. Map our generated machine code to NPU operations")
        logger.info("   2. Create buffer objects for data transfer")
        logger.info("   3. Execute kernels on actual hardware")
    else:
        logger.error("\n❌ Could not access NPU hardware")
    
    # Also test XRT
    logger.info("\n🔍 Testing XRT compatibility...")
    test_xrt_with_npu()

if __name__ == "__main__":
    main()