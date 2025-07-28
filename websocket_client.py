import asyncio
import websockets
import json

class WebSocketClient:
    def __init__(self, uri, client_id):
        self.uri = uri
        self.client_id = client_id
        self.websocket = None
        self.event_queue = asyncio.Queue()  # 用于消息事件的队列

    async def connect(self):
        while True:
            try:
                # 尝试连接到 WebSocket 服务器
                self.websocket = await websockets.connect(self.uri)
                print("Connected to server")

                # 连接后发送身份声明
                await self.websocket.send(json.dumps({"client_id": self.client_id}))

                # 持续监听消息
                await self.listen()

            except Exception as e:
                print(f"Connection failed: {e}")
                print("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    async def send_message(self, target_id, message):
        if self.websocket:
            await self.websocket.send(json.dumps({"target_id": target_id, "message": message}))
            print(f"Sent message to {target_id}: {message}")

    async def listen(self):
        try:
            async for message in self.websocket:
                # 当收到消息时，触发事件，将消息放入事件队列
                await self.on_message(message)
                await self.event_queue.put(message)  # 放入队列中供其他程序监听
        except websockets.ConnectionClosed:
            print("Connection closed, attempting to reconnect...")

    async def close(self):
        if self.websocket:
            await self.websocket.close()

    # 可重写的消息处理函数
    async def on_message(self, message):
        """重写此函数以处理收到的消息"""
        print(f"Received message: {message}")

    async def get_event(self):
        """其他程序可以通过这个方法来监听消息事件"""
        loop = asyncio.get_event_loop()  # 确认在当前事件循环中运行
        return await self.event_queue.get()  # 从队列中获取消息

if __name__ == "__main__":
    # async def interactive_input(client):
    #     while True:
    #         try:
    #             # 从用户那里获取 target_id 和 message
    #             target_id = await aioconsole.ainput("Enter target_id: ")
    #             message = await aioconsole.ainput("Enter message: ")

    #             # 发送用户输入的消息
    #             await client.send_message(target_id, message)
    #         except Exception as e:
    #             print(f"Failed to send message: {e}")

    async def main():
        # 定义 WebSocket 服务端的 URI 和客户端 ID
        uri = "ws://localhost:8765"
        client_id = "client_1"

        # 创建 WebSocketClient 实例
        client = WebSocketClient(uri, client_id)

        # 启动连接并保持连接
        connect_task = asyncio.create_task(client.connect())

        # 启动交互式消息输入
        # input_task = asyncio.create_task(interactive_input(client))

        # 确保任务不会立即退出
        await asyncio.gather(connect_task)

    asyncio.run(main())