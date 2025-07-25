import libtmux
import time
import os
import subprocess
import threading
from typing import Optional

class TmuxTerminal:
    """
    一个统一的、沉浸式的 tmux 终端会话。

    脚本启动后，用户终端会直接“变身”为 tmux 会话的监视器并保持。
    脚本在后台按顺序执行命令，用户可以实时、不间断地观看所有过程。
    """
    def __init__(self, session_name: str, start_dir: Optional[str] = None):
        self.session_name = session_name
        self.start_dir = os.path.abspath(start_dir or os.getcwd())
        self._server = libtmux.Server()
        self._session: Optional[libtmux.Session] = None
        self._pane: Optional[libtmux.Pane] = None
        self._attach_thread: Optional[threading.Thread] = None
        self._command_counter = 0  # 新增：命令执行计数器

    def __enter__(self):
        """进入上下文时，创建会话，定义辅助函数，并附加用户终端。"""
        print("--- [正在启动并进入 Tmux 终端...] ---")
        if self._server.has_session(self.session_name):
            self._server.kill_session(self.session_name)
        
        self._session = self._server.new_session(
            session_name=self.session_name,
            start_directory=self.start_dir
        )
        self._pane = self._session.active_window.active_pane
        time.sleep(0.5)

        helper_func = 'run() { channel_name="$1"; shift; "$@"; tmux wait-for -S "$channel_name"; }'
        self._pane.send_keys(helper_func, enter=True)

        self._pane.clear()

        def _attach_in_background():
            subprocess.run(
                ['tmux', 'attach-session', '-t', self.session_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        self._attach_thread = threading.Thread(target=_attach_in_background)
        self._attach_thread.start()
        
        time.sleep(0.5)
        print("--- [连接成功！脚本现在将在下方的 Tmux 终端中执行命令] ---")
        time.sleep(1)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("--- [正在关闭 Tmux 终端...] ---")
        if self._server.has_session(self.session_name) and self._attach_thread.is_alive():
            self._server.cmd('detach-client', '-s', self.session_name)
        
        self._attach_thread.join(timeout=2)
        
        if self._server.has_session(self.session_name):
            self._server.kill_session(self.session_name)
        print("--- [终端已关闭] ---")

    def execute(self, command_string: str):
        """
        在已附加的 tmux 终端中执行单个命令，并等待其完成。
        """
        if not self._pane or not self._attach_thread.is_alive():
            raise RuntimeError("Terminal is not running or attached.")

        print(f"[脚本日志] 正在执行: {command_string}")

        # 使用计数器代替 uuid
        channel_name = f"tmux-wait-{self._command_counter}"
        self._command_counter += 1  # 计数器加一，为下次调用做准备
        
        full_command = f"run {channel_name} {command_string}"

        self._pane.send_keys(full_command, enter=True)
        
        try:
            self._server.cmd('wait-for', channel_name)
        except Exception as e:
            print(f"[!!] 等待命令 '{command_string}' 完成时出错: {e}")

    def wait_for_key(self, message: str = "所有任务已完成。"):
        """
        在 tmux 窗格中显示一条消息，并暂停脚本，等待用户按键。
        """
        final_prompt_cmd = f"echo; echo '--- {message} 按 Enter 键退出 ---'; echo"
        self._pane.send_keys(final_prompt_cmd, enter=True)
        
        input("\n[脚本日志] 按 Enter 键以关闭并清理 Tmux 终端...")

# --- 使用示例 ---
if __name__ == "__main__":
    try:
        with TmuxTerminal(session_name="clean-immersive-demo") as term:
            term.execute("echo '欢迎！命令将在这里无缝执行。'")
            term.execute("sleep 1")
            
            # 回显将是 'run tmux-wait-2 ...'
            term.execute("echo '你看，即使是很长很长的一段话，回显也很干净。'")
            term.execute("sleep 1")

            term.execute("sudo echo 'Sudo 已验证。'")
            
            term.execute("ls -l")
            term.execute("sleep 1")
            
            term.wait_for_key()

    except FileNotFoundError:
        print("\n[!!] 致命错误: 'tmux' 命令未找到。请确保 tmux 已安装并位于您的 PATH 中。")
    except Exception as e:
        print(f"\n[!!] 发生未处理的异常: {e}")