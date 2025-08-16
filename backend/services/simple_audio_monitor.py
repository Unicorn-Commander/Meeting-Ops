#!/usr/bin/env python3
"""
Simple Audio Monitor Service
Runs in the main event loop without threading complications
"""

import asyncio
import json
import logging
import redis.asyncio as redis
from datetime import datetime
from typing import Optional
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

logger = logging.getLogger(__name__)

class SimpleAudioMonitor:
    """Simple audio monitoring that runs in main event loop"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.monitoring_task = None
        self.is_monitoring = False
        self.usb_monitor = None
        
    async def start(self):
        """Start audio monitoring"""
        if self.is_monitoring:
            return True
            
        try:
            # Connect to Redis
            self.redis_client = await redis.from_url(
                "redis://localhost:6379", 
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("✅ Connected to Redis for audio monitoring")
            
            # Start monitoring task
            self.monitoring_task = asyncio.create_task(self._monitor_loop())
            self.is_monitoring = True
            
            logger.info("🎤 Simple audio monitoring started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start audio monitor: {e}")
            return False
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        # Import USB monitor
        try:
            from audio_level_direct_usb import DirectUSBAudioMonitor
            self.usb_monitor = DirectUSBAudioMonitor()
            use_real = True
        except ImportError:
            logger.warning("USB monitor not available, using simulation")
            use_real = False
            
        usb_active = False
        
        while self.is_monitoring:
            try:
                # Check if recording is active
                recording_active = await self.redis_client.get("recording:active")
                
                if recording_active:
                    # Recording active - stop USB monitor
                    if usb_active and self.usb_monitor:
                        logger.info("📼 Recording active, pausing USB monitor")
                        await self.usb_monitor.stop_monitoring()
                        usb_active = False
                    
                    # Send simulated levels
                    import random
                    level = 0.3 + random.random() * 0.4
                    
                    await self.redis_client.publish("audio:levels", json.dumps({
                        "type": "audio_level",
                        "level": level,
                        "peak": level + 0.1,
                        "db": -40 + random.random() * 20,
                        "timestamp": datetime.now().isoformat(),
                        "device": "Recording Active",
                        "real": False
                    }))
                    
                else:
                    # No recording - use real USB monitor
                    if use_real and self.usb_monitor:
                        # Start USB monitor if not active
                        if not usb_active:
                            logger.info("🎤 Starting USB audio monitor")
                            started = await self.usb_monitor.start_monitoring()
                            if started:
                                usb_active = True
                            else:
                                use_real = False
                        
                        # Get real audio level
                        if usb_active:
                            level_data = await self.usb_monitor.get_audio_level()
                            
                            await self.redis_client.publish("audio:levels", json.dumps({
                                "type": "audio_level",
                                "level": level_data.get("level", 0),
                                "peak": level_data.get("peak", 0),
                                "db": level_data.get("db", -60),
                                "timestamp": level_data.get("timestamp"),
                                "device": "USB PnP Sound Device",
                                "real": True
                            }))
                    else:
                        # Simulated fallback
                        import random
                        import math
                        import time
                        
                        base = 0.1 + abs(math.sin(time.time() * 0.3)) * 0.2
                        level = base + random.random() * 0.05
                        
                        await self.redis_client.publish("audio:levels", json.dumps({
                            "type": "audio_level",
                            "level": level,
                            "peak": level + 0.1,
                            "db": 20 * math.log10(level + 1e-10),
                            "timestamp": datetime.now().isoformat(),
                            "device": "Simulated",
                            "real": False
                        }))
                
                # Update rate: 10 Hz
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(1)
        
        # Cleanup
        if self.usb_monitor and usb_active:
            try:
                await self.usb_monitor.stop_monitoring()
            except:
                pass
    
    async def stop(self):
        """Stop monitoring"""
        self.is_monitoring = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self.redis_client:
            await self.redis_client.close()
            
        logger.info("🎤 Audio monitoring stopped")

# Global instance
simple_audio_monitor = SimpleAudioMonitor()

async def start_simple_audio_monitoring():
    """Start the global audio monitor"""
    return await simple_audio_monitor.start()

async def stop_simple_audio_monitoring():
    """Stop the global audio monitor"""
    await simple_audio_monitor.stop()

if __name__ == "__main__":
    # Test the monitor
    async def test():
        print("Testing Simple Audio Monitor")
        print("=" * 50)
        
        monitor = SimpleAudioMonitor()
        if await monitor.start():
            print("✅ Monitoring started")
            await asyncio.sleep(10)
            await monitor.stop()
            print("✅ Test complete")
        else:
            print("❌ Failed to start")
    
    asyncio.run(test())