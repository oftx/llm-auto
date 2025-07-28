import asyncio
import websockets
import json

class WebSocketServer:
    connected_clients = {}

    def __init__(self, host='localhost', port=8765, on_message_callback=None):
        self.host = host
        self.port = port
        self.server = None
        self.on_message_callback = on_message_callback  # 添加回调函数

    async def handle_client(self, websocket):
        try:
            # 接收客户端识别消息
            identification_msg = await websocket.recv()
            client_info = json.loads(identification_msg)

            if 'client_id' in client_info:
                client_id = client_info['client_id']
                WebSocketServer.connected_clients[websocket] = {"id": client_id}

                print(f"[+] {client_id}")

                # 给客户端一个确认消息
                await websocket.send(f"Welcome {client_id}")

                # 持续监听客户端消息
                async for message in websocket:
                    # 调用回调函数
                    if self.on_message_callback:
                        self.on_message_callback(message)  # 将收到的消息传递给回调函数

                    # 处理消息，根据消息中的目标客户端 ID 转发
                    await self.handle_message(message, client_id)

            else:
                await websocket.send("Error: Missing 'client_id' in identification message.")
                await websocket.close()

        except websockets.ConnectionClosed:
            print(f"Client disconnected unexpectedly: {WebSocketServer.connected_clients.get(websocket, {}).get('id', 'Unknown')}")
        finally:
            if websocket in WebSocketServer.connected_clients:
                client_id = WebSocketServer.connected_clients[websocket]['id']
                del WebSocketServer.connected_clients[websocket]
                print(f"[-] {client_id}")

    async def handle_message(self, message, sender_id):
        try:
            # 尝试解析消息为 JSON
            message_data = json.loads(message)
            target_id = message_data.get("target_id")
            text_message = message_data.get("message")

            if target_id and text_message:
                # 发送消息到目标客户端
                dumped_message = json.dumps({"s": sender_id, "m": json.loads(text_message)})
                if target_id == "Server": return
                success = await self.send_to_client(target_id, dumped_message)

                if not success:
                    await self.send_error(sender_id, "Error: Target client not found.")
            else:
                # 如果消息格式不正确，发送错误信息回客户端
                await self.send_error(sender_id, "Error: Invalid message format.")
        except json.JSONDecodeError:
            await self.send_error(sender_id, "Error: Failed to decode message.")

    async def send_to_client(self, target_id, message):
        # 查找目标客户端
        found = False
        for client_websocket, client_info in WebSocketServer.connected_clients.items():
            if client_info["id"] == target_id:
                try:
                    await client_websocket.send(message)
                    found = True
                    break
                except websockets.ConnectionClosed:
                    # 如果目标客户端连接关闭，移除它
                    del WebSocketServer.connected_clients[client_websocket]

        # 返回是否成功找到目标客户端
        return found

    async def send_error(self, sender_id, error_message):
        # 向发送者客户端发送错误信息
        for client_websocket, client_info in WebSocketServer.connected_clients.items():
            if client_info["id"] == sender_id:
                try:
                    await client_websocket.send(error_message)
                    return
                except websockets.ConnectionClosed:
                    # 如果发送者连接关闭，移除它
                    del WebSocketServer.connected_clients[client_websocket]

    # 启动 WebSocket 服务器
    async def start(self):
        self.server = await websockets.serve(self.handle_client, self.host, self.port)
        print(f"WebSocket server started on ws://{self.host}:{self.port}")
        await asyncio.Future()  # 保持服务器运行

    # 停止 WebSocket 服务器
    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            print("WebSocket server stopped")

# 示例回调函数
def custom_message_handler(message):
    print(f"Custom handler received message: {message}")

# 如果需要单独启动，可以加入入口
if __name__ == "__main__":
    ws_server = WebSocketServer(on_message_callback=custom_message_handler)
    asyncio.run(ws_server.start())
