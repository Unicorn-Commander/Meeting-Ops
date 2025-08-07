# Meeting-Ops Hardware Specifications

## Default USB Microphone: Mini USB Microphone M-305

### Specifications
- **Model**: M-305
- **Mic Unit**: Condenser
- **Directional Pattern**: Omnidirectional
- **Sensitivity**: -48dB ± 3dB
- **Impedance**: ≤ 2.2KΩ
- **Operation Voltage**: 2V
- **Maximum Sound Pressure Level**: 100dB
- **Signal-to-Noise Ratio**: >58dB
- **Frequency Response**: 100Hz - 8KHz
- **Plug Type**: USB 2.0
- **Dimensions**: 22×18×7mm (0.9×0.7×0.3 inches)
- **Weight**: 2 grams (0.07 oz)
- **Origin**: Made in China

### Features
- **Portable**: Leave plugged into your laptop
- **Plug and Play**: No driver installation required
- **Noise Cancelling**: Filters out background noise
- **Wide Compatibility**: Gaming, recording, communication
- **USB Powered**: No external power required

### Optimal Settings for Meeting-Ops
- **Sample Rate**: 8kHz (proper Nyquist sampling for 8kHz max frequency)
- **Channels**: Mono (1 channel)
- **Bit Depth**: 16-bit
- **Format**: PCM/WAV
- **Buffer Size**: 1024 samples for low latency

### Audio Device Detection
The system automatically detects available audio input devices and allows selection from a dropdown menu. The M-305 typically appears as:
- "USB PnP Sound Device"
- "USB Audio Device" 
- "Mini USB Microphone"

### Troubleshooting
- Ensure USB connection is secure
- Check system audio permissions
- Verify device appears in `arecord -l` output
- Test with `arecord -D hw:0,0 -f S16_LE -r 8000 -c 1 test.wav`
EOF < /dev/null
