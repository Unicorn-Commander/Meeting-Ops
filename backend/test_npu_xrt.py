#!/usr/bin/env python3
"""
Test NPU using XRT Python API
"""

import os
import sys
import numpy as np

# Add XRT Python path
sys.path.insert(0, '/opt/xilinx/xrt/python')

try:
    import pyxrt
    print("✅ PyXRT imported successfully")
except ImportError as e:
    print(f"❌ Failed to import pyxrt: {e}")
    print("Make sure XRT is installed and sourced")
    sys.exit(1)

def test_npu():
    """Test NPU using XRT API"""
    try:
        # List devices
        device_count = pyxrt.device.get_count()
        print(f"\n🔍 Found {device_count} device(s)")
        
        if device_count == 0:
            print("❌ No devices found")
            return False
            
        # Open first device
        device = pyxrt.device(0)
        print(f"✅ Opened device 0")
        
        # Get device info
        device_name = device.get_info(pyxrt.xrt_info_device.name)
        print(f"📱 Device name: {device_name}")
        
        # Load xclbin
        xclbin_path = "/home/ucadmin/Development/xdna-driver/tools/bins/1502_00/validate.xclbin"
        if os.path.exists(xclbin_path):
            print(f"\n📦 Loading xclbin: {xclbin_path}")
            xclbin = pyxrt.xclbin(xclbin_path)
            uuid = device.load_xclbin(xclbin)
            print(f"✅ Xclbin loaded, UUID: {uuid}")
            
            # Create kernel
            kernels = xclbin.get_kernels()
            if kernels:
                kernel_name = kernels[0].get_name()
                print(f"\n🎯 Creating kernel: {kernel_name}")
                kernel = pyxrt.kernel(device, uuid, kernel_name)
                print(f"✅ Kernel created")
                
                # Allocate buffers
                print("\n💾 Allocating buffers...")
                bo_in = pyxrt.bo(device, 4096, pyxrt.bo.flags.normal, kernel.group_id(0))
                bo_out = pyxrt.bo(device, 4096, pyxrt.bo.flags.normal, kernel.group_id(1))
                print("✅ Buffers allocated")
                
                # Map and fill input buffer
                buf_in = np.asarray(bo_in.map())
                buf_in[:] = np.random.randint(0, 255, size=buf_in.shape, dtype=np.uint8)
                bo_in.sync(pyxrt.xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE)
                
                # Run kernel
                print("\n⚡ Running kernel...")
                run = kernel(bo_in, bo_out, 1024)
                run.wait()
                print("✅ Kernel execution completed")
                
                # Read results
                bo_out.sync(pyxrt.xclBOSyncDirection.XCL_BO_SYNC_BO_FROM_DEVICE)
                buf_out = np.asarray(bo_out.map())
                print(f"📊 Output buffer first 10 bytes: {buf_out[:10]}")
                
                print("\n🎉 NPU test successful!")
                return True
            else:
                print("❌ No kernels found in xclbin")
        else:
            print(f"❌ Xclbin not found: {xclbin_path}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔥 Testing NPU with XRT Python API")
    print("=" * 50)
    
    # Set XRT verbosity for debugging
    os.environ['XRT_VERBOSITY'] = '6'
    
    success = test_npu()
    
    if success:
        print("\n✅ All tests passed! NPU is working correctly.")
    else:
        print("\n❌ NPU test failed.")