#!/usr/bin/env python3
"""
Test NPU via XRT (Xilinx Runtime) APIs
======================================
Using the proper XRT C++ API through Python
"""

import sys
import os
import numpy as np
import logging
from pathlib import Path

# Add XRT Python path
sys.path.insert(0, '/opt/xilinx/xrt/python')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_xrt_npu():
    """Test NPU using XRT Python bindings"""
    try:
        import pyxrt
        logger.info("✅ PyXRT module loaded successfully")
        
        # List devices
        device_count = pyxrt.device.probe()
        logger.info(f"Found {device_count} XRT devices")
        
        if device_count > 0:
            # Open first device
            device = pyxrt.device(0)
            logger.info(f"✅ Opened device: {device}")
            
            # Get device info
            name = device.get_info(pyxrt.info.device.name)
            logger.info(f"Device name: {name}")
            
            # Check for NPU
            bdf = device.get_info(pyxrt.info.device.bdf)
            logger.info(f"Device BDF: {bdf}")
            
            return True
            
    except ImportError:
        logger.error("❌ PyXRT module not found")
    except Exception as e:
        logger.error(f"❌ XRT error: {e}")
    
    return False

def test_xrt_core():
    """Test using XRT core library directly"""
    try:
        # Try using ctypes to load XRT core
        import ctypes
        
        # Load XRT core library
        xrt_core = ctypes.CDLL("/opt/xilinx/xrt/lib/libxrt_core.so")
        logger.info("✅ Loaded libxrt_core.so")
        
        # Try xclProbe
        xrt_core.xclProbe.restype = ctypes.c_uint
        device_count = xrt_core.xclProbe()
        logger.info(f"xclProbe returned: {device_count} devices")
        
        if device_count > 0:
            # Define xclOpen
            xrt_core.xclOpen.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.c_int]
            xrt_core.xclOpen.restype = ctypes.c_void_p
            
            # Open device 0
            handle = xrt_core.xclOpen(0, None, 0)
            if handle:
                logger.info(f"✅ Opened device handle: {handle}")
                
                # Close device
                xrt_core.xclClose.argtypes = [ctypes.c_void_p]
                xrt_core.xclClose(handle)
                logger.info("✅ Closed device")
                
                return True
        
    except Exception as e:
        logger.error(f"XRT core error: {e}")
    
    return False

def test_xrt_driver_xdna():
    """Test XDNA-specific XRT driver"""
    try:
        import ctypes
        
        # Try loading XDNA driver
        xrt_xdna = ctypes.CDLL("/usr/local/xrt/lib/libxrt_driver_xdna.so")
        logger.info("✅ Loaded libxrt_driver_xdna.so")
        
        # This driver should work with /dev/accel/accel0
        return True
        
    except Exception as e:
        logger.error(f"XDNA driver error: {e}")
    
    return False

def check_xrt_environment():
    """Check XRT environment setup"""
    logger.info("\n🔍 Checking XRT environment...")
    
    # Check environment variables
    xrt_path = os.environ.get("XILINX_XRT")
    if xrt_path:
        logger.info(f"XILINX_XRT = {xrt_path}")
    else:
        logger.warning("XILINX_XRT not set")
        os.environ["XILINX_XRT"] = "/opt/xilinx/xrt"
        logger.info("Set XILINX_XRT = /opt/xilinx/xrt")
    
    # Check for xrt.ini
    xrt_ini = Path("/opt/xilinx/xrt/xrt.ini")
    if xrt_ini.exists():
        logger.info("✅ Found xrt.ini")
    else:
        logger.warning("⚠️ xrt.ini not found")
    
    # Check device permissions
    accel_dev = Path("/dev/accel/accel0")
    if accel_dev.exists():
        logger.info(f"✅ NPU device exists: {accel_dev}")
        # Check if we can access it
        try:
            with open(accel_dev, 'rb') as f:
                logger.info("✅ NPU device is accessible")
        except Exception as e:
            logger.error(f"❌ Cannot access NPU device: {e}")
    else:
        logger.error("❌ NPU device not found")

def main():
    logger.info("=" * 60)
    logger.info("XRT NPU TEST - PROPER API ACCESS")
    logger.info("=" * 60)
    
    # Check environment
    check_xrt_environment()
    
    # Test different approaches
    logger.info("\n1️⃣ Testing PyXRT...")
    if test_xrt_npu():
        logger.info("✅ PyXRT working!")
    
    logger.info("\n2️⃣ Testing XRT Core...")
    if test_xrt_core():
        logger.info("✅ XRT Core working!")
    
    logger.info("\n3️⃣ Testing XDNA Driver...")
    if test_xrt_driver_xdna():
        logger.info("✅ XDNA driver loaded!")
    
    logger.info("\n📌 Summary:")
    logger.info("The NPU hardware is present but XRT may need configuration")
    logger.info("to properly detect the /dev/accel/accel0 device.")

if __name__ == "__main__":
    main()