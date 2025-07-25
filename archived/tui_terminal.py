import asyncio
import os
import pty
import termios
from typing import Dict, List

from rich.text import Text
from textual.app import App, ComposeResult
from textual.events import Key
from textual.widgets import Header, Footer, RichLog

# --- Configuration Constants ---
ESSENTIAL_VARS: List[str] = [
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE"
]
SHELL_PROMPT: str = r"\[\033[01;32m\]\w\[\033[00m\] \$ "


class PerfectTerminalApp(App):
    """
    一个真正的终端模拟器，通过正确配置PTY为“半原始模式”(cbreak mode)，
    实现了行编辑、退格键以及由终端驱动控制的回显功能。
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]
    # CSS_PATH = "tui_terminal.css" # 如果您有CSS文件，可以取消注释

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
        self.log_widget.write("[b]Initializing raw mode PTY shell session...[/b]")
        self.screen.can_focus = True
        self.screen.focus()
        await self._start_shell_in_pty()

    async def _start_shell_in_pty(self):
        master_fd, slave_fd = pty.openpty()
        self.pty_master_fd = master_fd

        self.original_termios = termios.tcgetattr(master_fd)
        attrs = termios.tcgetattr(master_fd)

        # --- 核心修复点: 重新开启本地回显 ---
        # 我们需要终端驱动来回显我们输入的字符，因为我们启动的bash shell不处理这个。
        # 模式: 关闭规范模式 (ICANON)，开启本地回显 (ECHO)。
        # 这通常被称为 "cbreak" 模式。
        attrs[3] &= ~termios.ICANON
        attrs[3] |= termios.ECHO  # <--- 关键修复！从 &= ~ (关闭) 改回 |= (开启)

        termios.tcsetattr(master_fd, termios.TCSADRAIN, attrs)

        sandboxed_env = self._create_sandboxed_environment()

        self.shell_process = await asyncio.create_subprocess_exec(
            "bash", "--norc", "--noprofile",
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            env=sandboxed_env, start_new_session=True
        )

        loop = asyncio.get_running_loop()
        loop.add_reader(self.pty_master_fd, self._read_from_pty)
        os.close(slave_fd)

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
                self.log_widget.write(rich_text)
        except OSError:
            pass

    async def on_key(self, event: Key) -> None:
        """
        这个健壮的按键处理函数是让ECHO模式正常工作的关键。
        它能正确处理功能键和可打印字符。
        """
        if self.pty_master_fd is not None:
            if event.key == "enter":
                os.write(self.pty_master_fd, b'\r')
            elif event.key == "backspace":
                os.write(self.pty_master_fd, b'\x7f')
            elif event.character:
                os.write(self.pty_master_fd, event.character.encode('utf-8'))

    async def action_quit(self) -> None:
        if self.pty_master_fd:
            asyncio.get_running_loop().remove_reader(self.pty_master_fd)
            if self.original_termios:
                termios.tcsetattr(self.pty_master_fd, termios.TCSADRAIN, self.original_termios)
            os.close(self.pty_master_fd)
            self.pty_master_fd = None

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