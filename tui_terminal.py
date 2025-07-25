import asyncio
import os
import pty
import tty
import termios # 我们将更深入地使用这个模块
from typing import Dict, List

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.events import Key
from textual.widgets import Header, Footer, RichLog

# --- Configuration Constants ---
ESSENTIAL_VARS: List[str] = [
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE"
]
SHELL_PROMPT: str = r"\[\033[01;32m\]\w\[\033[00m\] \$ "


class PerfectTerminalApp(App):
    """
    A true terminal emulator that manually configures the PTY mode
    to support line editing, backspace, and local echo of typed commands.
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]
    CSS_PATH = "tui_terminal.css"

    def __init__(self):
        super().__init__()
        self.shell_process: asyncio.subprocess.Process | None = None
        self.pty_master_fd: int | None = None
        self.original_termios: list | None = None
        self.log_widget = RichLog(id="log", highlight=True, markup=True, wrap=True)

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.log_widget
        yield Footer()

    async def on_mount(self) -> None:
        self.log_widget.write("[b]Initializing semi-raw mode PTY shell session...[/b]")
        self.screen.can_focus = True
        self.screen.focus()
        await self._start_shell_in_pty()

    async def _start_shell_in_pty(self):
        master_fd, slave_fd = pty.openpty()
        self.pty_master_fd = master_fd

        # *** 核心修复点: 手动配置终端模式 ***
        
        # 1. 保存原始终端设置，以便在退出时恢复
        self.original_termios = termios.tcgetattr(master_fd)
        
        # 2. 获取当前的终端属性
        attrs = termios.tcgetattr(master_fd)

        # 3. 修改属性以创建一个“半生不熟”的模式
        #    关闭规范模式 (ICANON): 不再需要按回车才发送整行
        #    开启本地回显 (ECHO): 让我们能看到自己输入的字符
        attrs[3] &= ~termios.ICANON  # c_lflag index
        attrs[3] |= termios.ECHO      # c_lflag index
        
        # 4. 应用修改后的设置
        termios.tcsetattr(master_fd, termios.TCSADRAIN, attrs)

        sandboxed_env = self._create_sandboxed_environment()

        self.shell_process = await asyncio.create_subprocess_exec(
            "bash", "--norc", "--noprofile",
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            env=sandboxed_env, start_new_session=True
        )

        loop = asyncio.get_running_loop()
        loop.add_reader(self.pty_master_fd, self._read_from_pty)

    def _create_sandboxed_environment(self) -> Dict[str, str]:
        clean_env: Dict[str, str] = {}
        for var in ESSENTIAL_VARS:
            if var in os.environ:
                clean_env[var] = os.environ[var]

        clean_env["TERM"] = "xterm-256color"
        clean_env["PS1"] = SHELL_PROMPT
        return clean_env

    def _read_from_pty(self) -> None:
        try:
            data = os.read(self.pty_master_fd, 1024)
            if data:
                rich_text = Text.from_ansi(data.decode('utf-8', errors='replace'))
                self.log_widget.write(rich_text, scroll_end=True)
        except OSError:
            pass
            
    async def on_key(self, event: Key) -> None:
        if self.pty_master_fd is not None and event.character:
            os.write(self.pty_master_fd, event.character.encode('utf-8'))

    async def action_quit(self) -> None:
        """Gracefully shuts down, CRITICALLY restoring original terminal settings."""
        if self.pty_master_fd:
            asyncio.get_running_loop().remove_reader(self.pty_master_fd)
            
            if self.original_termios:
                termios.tcsetattr(self.pty_master_fd, termios.TCSADRAIN, self.original_termios)
            
            os.close(self.pty_master_fd)

        if self.shell_process and self.shell_process.returncode is None:
            self.shell_process.terminate()
            await self.shell_process.wait()

        self.exit()


if __name__ == "__main__":
    if os.name != "posix":
        print("This application requires a POSIX-like OS (Linux, macOS) for 'pty', 'tty', and 'termios' modules.")
    else:
        app = PerfectTerminalApp()
        app.run()