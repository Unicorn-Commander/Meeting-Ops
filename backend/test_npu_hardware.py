#!/usr/bin/env python3
"""Test NPU hardware availability"""
import os
os.environ['LD_PRELOAD'] = '/lib/x86_64-linux-gnu/libstdc++.so.6'

print("🧪 Testing NPU Hardware Access")
print("=" * 50)

# Test PyXRT
print("\n1️⃣ Testing PyXRT...")
try:
    import pyxrt
    print("   ✅ PyXRT imported successfully")
    
    # Check for devices
    print("\n2️⃣ Checking for NPU devices...")
    try:
        num_devices = pyxrt.device.get_num_devices()
        print(f"   Found {num_devices} XRT devices")
        
        if num_devices > 0:
            for i in range(num_devices):
                device = pyxrt.device(i)
                print(f"   Device {i}: {device.get_info(pyxrt.device.info.NAME)}")
        else:
            print("   ❌ No XRT devices found")
            
    except Exception as e:
        print(f"   ❌ Error checking devices: {e}")
        
except ImportError as e:
    print(f"   ❌ PyXRT not available: {e}")

# Test AIE2 kernel driver
print("\n3️⃣ Testing AIE2 Kernel Driver...")
try:
    from npu_optimization.aie2_kernel_driver import AIE2KernelDriver
    driver = AIE2KernelDriver()
    print("   ✅ AIE2 driver created")
    
    # Try to initialize
    if driver.initialize_npu():
        print("   ✅ NPU initialized!")
        print(f"   Device info: {driver.device}")
    else:
        print("   ❌ NPU initialization failed (expected without v++)")
        
except Exception as e:
    print(f"   ❌ Error with AIE2 driver: {e}")

# Check kernel module
print("\n4️⃣ Checking kernel module...")
import subprocess
result = subprocess.run(['lsmod'], capture_output=True, text=True)
if 'amdxdna' in result.stdout:
    print("   ✅ amdxdna kernel module loaded")
else:
    print("   ❌ amdxdna kernel module not found")

# Check for NPU in system
print("\n5️⃣ Checking system devices...")
result = subprocess.run(['ls', '-la', '/dev/accel/'], capture_output=True, text=True)
if result.returncode == 0:
    print("   ✅ Accelerator devices found:")
    print(result.stdout)
else:
    print("   ❌ No accelerator devices in /dev/")

print("\n" + "=" * 50)
print("Test complete!")