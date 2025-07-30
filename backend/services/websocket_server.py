import asyncio
import websockets
import json
import threading
from .audio_capture import audio_capture_service

class WebSocketServer:
    def __init__(self, port=8765):
        self.port = port
        self.clients = set()
        self.server = None
        self.running = False
        self.thread = None

    async def handler(self, websocket):
        self.clients.add(websocket)
        try:
            async for message in websocket:
                # Clients can send keep-alive messages
                pass
        finally:
            self.clients.remove(websocket)

    async def broadcast(self, message):
        if self.clients:
            await asyncio.gather(
                *[client.send(message) for client in self.clients]
            )

    async def start_server(self):
        self.server = await websockets.serve(self.handler, "0.0.0.0", self.port)
        self.running = True
        print(f"WebSocket server started on port {self.port}")
        await self.server.wait_closed()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        asyncio.run(self.start_server())

    def send_audio_level(self, level):
        if self.running and self.clients:
            message = json.dumps({"type": "audio_level", "level": level})
            asyncio.run(self.broadcast(message))

# Singleton instance
websocket_server = WebSocketServer()

def start_websocket_server():
    websocket_server.start()
