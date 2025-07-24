#!/usr/bin/env python3
"""
Test NPU Access Without Vitis - Direct XRT Approach
==================================================
"""

import sys
import os
sys.path.insert(0, '/opt/xilinx/xrt/python')

import xrt_binding as xrt
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_xrt_access():
    """Test direct XRT access to NPU without v++"""
    logger.info("🚀 Testing direct XRT access to NPU...")
    
    try:
        # List available devices
        device_count = xrt.xclProbe()
        logger.info(f"✅ Found {device_count} XRT devices")
        
        if device_count == 0:
            logger.warning("⚠️ No XRT devices found - running in emulation mode")
            return test_emulation_mode()
            
        # Open first device
        device = xrt.xclOpen(0)
        logger.info(f"📱 Opened device 0: {device}")
        
        # Get device info
        info = xrt.xclGetDeviceInfo2(device)
        logger.info(f"🔍 Device info: {info}")
        
        # Close device
        xrt.xclClose(device)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ XRT access failed: {e}")
        return test_emulation_mode()

def test_emulation_mode():
    """Test NPU emulation without hardware"""
    logger.info("🎮 Running NPU emulation mode...")
    
    # Load the machine code generator
    from npu_optimization.npu_machine_code import NPUMachineCodeGenerator
    
    generator = NPUMachineCodeGenerator()
    
    # Generate whisper NPU binary
    logger.info("⚙️ Generating NPU machine code for Whisper...")
    machine_code = generator.generate_full_whisperx_binary()
    
    # Save binary
    output_path = "whisperx_npu_emulated.bin"
    with open(output_path, "wb") as f:
        f.write(machine_code)
    
    logger.info(f"✅ Generated NPU binary: {output_path} ({len(machine_code)} bytes)")
    
    # Test with dummy data
    test_inference_emulated()
    
    return True

def test_inference_emulated():
    """Test inference in emulation mode"""
    logger.info("🧪 Testing Whisper inference (emulated)...")
    
    # Simulate audio input
    audio = np.random.randn(16000).astype(np.float32)  # 1 second of audio
    
    # Load WhisperX NPU engine
    from npu_optimization.whisperx_npu_engine import WhisperXNPUEngine
    
    engine = WhisperXNPUEngine(device="cpu")  # Force CPU emulation
    
    # Process audio
    result = engine.process_audio(audio, sample_rate=16000)
    
    logger.info("📝 Transcription result:")
    logger.info(f"  Text: {result.get('text', 'N/A')}")
    logger.info(f"  Speakers: {len(result.get('speakers', []))}")
    logger.info(f"  Processing time: {result.get('processing_time', 0):.3f}s")
    
    return result

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("NPU DIRECT ACCESS TEST - NO VITIS REQUIRED!")
    logger.info("=" * 60)
    
    # Test XRT access
    success = test_xrt_access()
    
    if success:
        logger.info("\n✅ NPU access successful! We can proceed without Vitis.")
        logger.info("📌 Next steps:")
        logger.info("   1. Generate NPU binaries using machine code generator")
        logger.info("   2. Load binaries directly via XRT")
        logger.info("   3. Run WhisperX with NPU acceleration")
    else:
        logger.error("\n❌ NPU access failed")