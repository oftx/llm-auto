import asyncio
import json
import traceback
from typing import List, Union, Any
from tmux_cmd_runner import TmuxTerminal, CommandResult
from websocket_client import WebSocketClient

async def run_cmd_and_get_result(term: TmuxTerminal, cmd: Union[str, List[str]]) -> Any:
    """
    在一个独立的线程中运行阻塞的命令并获取结果，以避免阻塞事件循环。

    Args:
        term: TmuxTerminal 实例。
        cmd: 要执行的命令字符串或列表。

    Returns:
        命令执行的结果。

    Raises:
        TypeError, ValueError, RuntimeError for command issues.
    """
    if not isinstance(cmd, (str, list)):
        raise TypeError(f"不支持的参数类型: {type(cmd)}! 期望 str 或 list.")

    if isinstance(cmd, str) and not cmd.strip():
        raise ValueError("命令字符串不应为空!")

    if isinstance(cmd, list) and not cmd:
        raise ValueError("命令列表不应为空!")

    try:
        await asyncio.to_thread(term.execute, cmd)
        result = await asyncio.to_thread(CommandResult.get)
        return result

    except Exception as e:
        # 将底层的执行错误包装成一个运行时错误
        raise RuntimeError(f"命令执行期间发生错误: {e}") from e

async def execute_and_log_task(term: TmuxTerminal, commands: Union[str, List[str]], wsc: WebSocketClient, sender_id: str) -> None:
    """
    一个包装器，作为独立的后台任务运行。
    它调用非阻塞的命令执行函数并打印结果或错误。
    """
    # print(f"后台任务已创建：准备执行 '{str(commands)[:50]}...'")
    try:
        # 等待在独立线程中运行的命令完成
        result = await run_cmd_and_get_result(term, commands)
        # print(f"命令 '{str(commands)[:50]}...' 的结果是:")
        await wsc.send_message(sender_id, json.dumps({"success":True,"result":result}))
        print(result)
    except (TypeError, ValueError, RuntimeError) as e:
        await wsc.send_message(sender_id, json.dumps({"success":False}))
        print(f"命令处理中出现错误: {e}")
    except Exception as e:
        await wsc.send_message(sender_id, json.dumps({"success":False}))
        print(f"执行任务时发生未知错误: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    with TmuxTerminal(session_name="cmd-runner") as term:

        async def custom_on_message(self, message):
            """
            WebSocket 消息处理器。
            它只负责解析消息并创建后台任务，永远不会被阻塞。
            """
            try:
                msg_dict = json.loads(message)
                commands = msg_dict['m']['data']
                sender_id = msg_dict['s']
                if term.is_running_cmd:
                    await self.send_message(sender_id, json.dumps({"success":False}))
                    print("正在运行中，请稍后传入命令")
                    return
                asyncio.create_task(execute_and_log_task(term, commands, self, sender_id))
            except json.JSONDecodeError:
                print("传入数据格式错误! 消息必须是有效的 JSON。")
            except KeyError:
                print("出现 KeyError! JSON 结构应为 {'m': {'data': ...}}")
            except Exception as e:
                print(f"处理传入消息时发生错误: {e}")
                traceback.print_exc()

        WebSocketClient.on_message = custom_on_message

        async def main():
            wsc = WebSocketClient("ws://localhost:8765", "receiver")
            await wsc.connect()

        try:
            # print("客户端启动，等待来自 ws://localhost:8765 的命令...")
            # print("注意: `asyncio.to_thread` 在 Python 3.9+ 中可用。")
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n客户端关闭。")
        except RuntimeError as e:
            # 在某些环境中，事件循环关闭时可能会抛出此错误
            if "Event loop is closed" not in str(e):
                raise