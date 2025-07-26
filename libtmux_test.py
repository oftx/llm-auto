import libtmux
import os
from typing import Optional, List

class TmuxTerminal:
    """
    一个用于顺序执行命令的 tmux 会话管理器。

    脚本启动后，会创建一个独立的 tmux 会话，并提供连接命令。
    用户可以打开新的终端，连接到该会话，实时观察脚本在后台执行的命令。
    脚本结束后，会打印出完整的、清理过的会话输出。
    """
    def __init__(self, session_name: str, start_dir: Optional[str] = None):
        self.session_name = session_name
        self.start_dir = os.path.abspath(start_dir or os.getcwd())
        self._server = libtmux.Server()
        self._session: Optional[libtmux.Session] = None
        self._pane: Optional[libtmux.Pane] = None
        self._command_counter = 0

    def __enter__(self):
        """进入上下文时，创建或附加到会话，并提供连接指引。"""
        # 优化：不再需要先判断，get_or_create 行为更简洁
        self._session = self._server.find_where({"session_name": self.session_name})
        if not self._session:
            print(f"正在创建 Tmux 会话 '{self.session_name}'...")
            self._session = self._server.new_session(
                session_name=self.session_name,
                start_directory=self.start_dir
            )
        else:
            print(f"已连接到现有 Tmux 会话 '{self.session_name}'...")
        
        self._pane = self._session.active_window.active_pane
        # 仅在需要时清理，避免清除已有会话的内容
        # self._pane.clear()
        
        print(f"会话 '{self.session_name}' 已准备就绪。")
        print(f"✨ 可在新终端使用以下命令连接会话: tmux attach -t {self.session_name}\n")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时，打印最终输出并询问用户是否关闭会话。"""
        print("\n----------------------------------------")
        print("所有命令已执行完毕")
        print("----------------------------------------")
        
        # 新增：获取、清理并打印最终输出
        if self._pane:
            try:
                print("\n--- [以下是 Tmux 会话的最终输出内容] ---\n")
                # 捕获窗格中的所有行
                full_output: List[str] = self._pane.capture_pane()
                
                # 清理并打印输出，移除包含同步信令的行
                clean_output = [
                    line for line in full_output 
                    if 'tmux wait-for -S' not in line
                ]
                
                print('\n'.join(clean_output))
                print("\n--- [输出内容结束] ---\n")
            except Exception as e:
                print(f"[!!] 捕获最终输出时出错: {e}")

        # 询问用户是否要关闭会话，默认为 'N' (否)
        choice = input("是否需要关闭此 Tmux 会话？(y/N): ").lower().strip()
        
        if choice == 'y':
            print(f"正在关闭 Tmux 会话 '{self.session_name}'...")
            if self._server.has_session(self.session_name):
                self._server.kill_session(self.session_name)
            print("会话已关闭。")
        else:
            print(f"\n脚本已结束，Tmux 会话 '{self.session_name}' 仍在后台运行。")
            print(f"可使用 'tmux attach -t {self.session_name}' 重新连接。")
            print(f"或使用 'tmux kill-session -t {self.session_name}' 手动关闭。")

    def execute(self, command_string: str):
        """
        在 tmux 终端中执行单个命令，并等待其完成。
        """
        if not self._pane:
            raise RuntimeError("Tmux 会话尚未初始化。")

        print(f"> 正在执行: {command_string}")

        # 使用计数器生成唯一的通道名称
        channel_name = f"tmux-wait-{self._command_counter}"
        self._command_counter += 1
        
        # 1. 发送实际要执行的命令
        self._pane.send_keys(command_string, enter=True)
        
        # 2. 紧接着发送一个带信号的 wait-for 命令，它会在上一条命令结束后执行
        #    为了输出更干净，我们可以在命令前加上clear来清除上一条命令的回显
        self._pane.send_keys(f'tmux wait-for -S "{channel_name}"', enter=True)
        
        # 3. 在 Python 脚本中等待该信号，从而阻塞脚本直到 tmux 中的命令完成
        try:
            self._server.cmd('wait-for', channel_name)
        except Exception as e:
            print(f"[!!] 等待命令 '{command_string}' 完成时出错: {e}")

# --- 使用示例 ---
if __name__ == "__main__":
    try:
        # 使用 'with' 语句确保 __enter__ 和 __exit__ 方法被正确调用
        with TmuxTerminal(session_name="clean-output-demo") as term:
            # 清理屏幕，开始一个干净的会话
            term.execute("clear")
            term.execute("echo '欢迎！脚本已开始，命令将在此处顺序执行。'")
            term.execute("sleep 1")
            
            term.execute("echo '\n--- 任务 1：正在模拟耗时操作... ---' && sleep 2")
            term.execute("echo '--- 任务 2：正在列出当前目录文件... ---' && ls -l && sleep 1")
            
            term.execute("echo '\n所有任务已在 Tmux 中完成。'")

    except FileNotFoundError:
        print("\n[!!] 致命错误: 'tmux' 命令未找到。请确保 tmux 已安装并位于您的 PATH 中。")
    except Exception as e:
        print(f"\n[!!] 发生未处理的异常: {e}")