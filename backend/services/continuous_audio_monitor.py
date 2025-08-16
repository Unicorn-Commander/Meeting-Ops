#!/usr/bin/env python3
"""
Continuous Audio Level Monitor
Always-on audio monitoring that runs independently of recording
"""

import asyncio
import json
import logging
import redis.asyncio as redis
from datetime import datetime
from typing import Optional
import threading
import time

logger = logging.getLogger(__name__)

class ContinuousAudioMonitor:
    """Always-on audio level monitoring service"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.running = False
        self.monitor_thread = None
        self.usb_monitor = None
        self.paused_for_recording = False
        self._check_recording_interval = 0
        
    async def start(self):
        """Start continuous audio monitoring"""
        if self.running:
            logger.info("🎤 Audio monitor already running")
            return True
            
        try:
            # Connect to Redis
            self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info("✅ Connected to Redis for continuous audio monitoring")
            
            # Import and initialize USB monitor
            try:
                import sys
                import os
                sys.path.append(os.path.dirname(os.path.dirname(__file__)))
                from audio_level_direct_usb import DirectUSBAudioMonitor
                self.usb_monitor = DirectUSBAudioMonitor()
                use_real_audio = True
            except ImportError:
                logger.warning("DirectUSBAudioMonitor not available, using simulated levels")
                use_real_audio = False
                
            self.running = True
            
            # Start monitoring in separate thread to avoid blocking
            self.monitor_thread = threading.Thread(
                target=self._run_monitoring_loop,
                args=(use_real_audio,),
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info("🎤 Continuous audio monitoring started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start continuous audio monitor: {e}")
            return False
    
    def _run_monitoring_loop(self, use_real_audio: bool):
        """Run the monitoring loop in a separate thread"""
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._monitoring_loop(use_real_audio))
        except Exception as e:
            logger.error(f"Monitoring loop error: {e}")
        finally:
            loop.close()
    
    async def _monitoring_loop(self, use_real_audio: bool):
        """Main monitoring loop"""
        usb_monitor_active = False
        
        # Create Redis client for this thread's event loop
        local_redis = await redis.from_url(self.redis_url, decode_responses=True)
        
        logger.info(f"🎤 Audio monitoring loop started")
        
        try:
            while self.running:
                # Check if recording is active
                recording_active = await local_redis.get("recording:active") if local_redis else None
                
                if recording_active:
                    # Recording is active - stop USB monitor if running
                    if usb_monitor_active and self.usb_monitor:
                        logger.info("📼 Recording started - pausing USB monitor to free device")
                        await self.usb_monitor.stop_monitoring()
                        usb_monitor_active = False
                    
                    # Send simulated levels during recording
                    import random
                    import math
                    level = 0.3 + random.random() * 0.4  # Vary between 0.3-0.7
                    
                    await self._publish_audio_level({
                        'timestamp': datetime.now().isoformat(),
                        'level': level,
                        'peak': level + 0.1,
                        'db': 20 * math.log10(level + 1e-10),
                        'device': 'USB Device (Recording Active)',
                        'status': 'recording',
                        'real': False,
                        'continuous': True
                    }, local_redis)
                    
                else:
                    # No recording - start/resume USB monitoring
                    if use_real_audio and self.usb_monitor and not usb_monitor_active:
                        try:
                            logger.info("🎤 No recording active - starting USB monitor")
                            started = await self.usb_monitor.start_monitoring()
                            if started:
                                usb_monitor_active = True
                            else:
                                logger.warning("Failed to start USB monitor, using simulation")
                                use_real_audio = False
                        except Exception as e:
                            logger.error(f"Error starting USB monitor: {e}")
                            use_real_audio = False
                    
                    if use_real_audio and usb_monitor_active and self.usb_monitor:
                        # Get real audio levels
                        try:
                            level_data = await self.usb_monitor.get_audio_level()
                            await self._publish_audio_level({
                                'timestamp': level_data.get('timestamp', datetime.now().isoformat()),
                                'level': level_data.get('level', 0),
                                'peak': level_data.get('peak', 0),
                                'db': level_data.get('db', -60),
                                'device': 'USB PnP Sound Device',
                                'status': 'monitoring',
                                'real': True,
                                'continuous': True
                            }, local_redis)
                        except Exception as e:
                            logger.debug(f"USB read error: {e}")
                            # Continue monitoring even if occasional reads fail
                            await asyncio.sleep(0.1)
                            continue
                    else:
                        # Simulated levels for fallback
                        import random
                        import math
                        base_level = 0.1 + abs(math.sin(time.time() * 0.3)) * 0.2
                        noise = random.random() * 0.05
                        level = base_level + noise
                        
                        await self._publish_audio_level({
                            'timestamp': datetime.now().isoformat(),
                            'level': level,
                            'peak': level + 0.1,
                            'db': 20 * math.log10(level + 1e-10),
                            'device': 'Simulated Device',
                            'status': 'monitoring',
                            'real': False,
                            'continuous': True
                        }, local_redis)
                
                # Update every 100ms (10 Hz)
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Monitoring loop error: {e}")
        finally:
            # Clean up USB monitor
            if self.usb_monitor:
                try:
                    await self.usb_monitor.stop_monitoring()
                except:
                    pass
            # Close local Redis connection
            if local_redis:
                await local_redis.close()
    
    async def _publish_audio_level(self, level_data: dict, redis_client=None):
        """Publish audio level to Redis"""
        client = redis_client or self.redis_client
        if not client:
            return
            
        try:
            message = {
                "type": "audio_level",
                **level_data
            }
            await client.publish("audio:levels", json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to publish audio level: {e}")
    
    async def stop(self):
        """Stop continuous monitoring"""
        self.running = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
            
        if self.redis_client:
            await self.redis_client.close()
            
        logger.info("🎤 Continuous audio monitoring stopped")
    
    def is_running(self) -> bool:
        """Check if monitoring is running"""
        return self.running and (self.monitor_thread and self.monitor_thread.is_alive())

# Global instance
continuous_audio_monitor = ContinuousAudioMonitor()

async def start_continuous_audio_monitoring():
    """Start the global continuous audio monitor"""
    return await continuous_audio_monitor.start()

async def stop_continuous_audio_monitoring():
    """Stop the global continuous audio monitor"""
    await continuous_audio_monitor.stop()

def get_monitor_status() -> dict:
    """Get monitor status"""
    return {
        "running": continuous_audio_monitor.is_running(),
        "redis_connected": continuous_audio_monitor.redis_client is not None
    }

if __name__ == "__main__":
    # Test continuous monitoring
    async def test():
        print("🎤 Testing Continuous Audio Monitor")
        print("=" * 50)
        
        monitor = ContinuousAudioMonitor()
        if await monitor.start():
            print("✅ Monitoring started - running for 10 seconds...")
            await asyncio.sleep(10)
            await monitor.stop()
            print("✅ Test complete")
        else:
            print("❌ Failed to start monitoring")
    
    asyncio.run(test())