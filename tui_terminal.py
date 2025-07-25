import asyncio
import os
import pty
import termios  # 我们将更深入地使用这个模块
from typing import Dict, List

from rich.text import Text
from textual.app import App, ComposeResult
from textual.events import Key
from textual.widgets import Header, Footer, RichLog

# --- Configuration Constants ---
ESSENTIAL_VARS: List[str] = [
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE"
]
# 使用标准的bash彩色提示符
SHELL_PROMPT: str = r"\[\033[01;32m\]\w\[\033[00m\] \$ "


class PerfectTerminalApp(App):
    """
    一个真正的终端模拟器，通过正确配置PTY为“原始模式”(raw mode)，
    实现了行编辑、退格键以及由Shell控制的回显功能。
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]
    # 假设您的CSS文件与Python脚本在同一目录下
    # 如果您没有CSS文件，可以注释掉下面这行
    # CSS_PATH = "tui_terminal.css"

    def __init__(self):
        super().__init__()
        self.shell_process: asyncio.subprocess.Process | None = None
        self.pty_master_fd: int | None = None
        self.original_termios: list | None = None
        # RichLog是显示终端输出的理想组件
        self.log_widget = RichLog(id="log", highlight=True, markup=True, wrap=True)

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.log_widget
        yield Footer()

    async def on_mount(self) -> None:
        """组件挂载后，启动后台的Shell进程。"""
        self.log_widget.write("[b]Initializing raw mode PTY shell session...[/b]")
        self.screen.can_focus = True
        self.screen.focus()
        await self._start_shell_in_pty()

    async def _start_shell_in_pty(self):
        """在伪终端(PTY)中启动一个Shell进程，并正确配置其模式。"""
        master_fd, slave_fd = pty.openpty()
        self.pty_master_fd = master_fd

        # *** 核心修复点 1: 正确配置终端模式为“原始模式” ***
        
        # 1. 保存原始终端设置，以便在退出时恢复
        self.original_termios = termios.tcgetattr(master_fd)
        
        # 2. 获取当前的终端属性
        attrs = termios.tcgetattr(master_fd)

        # 3. 修改属性以创建一个“原始模式”(raw mode)
        #    关闭规范模式 (ICANON): 使得按键能被立即捕获，而不是等待回车。
        #    关闭本地回显 (ECHO): 这是关键！让Shell来决定如何回显字符。
        #    这样Shell才能正确处理退格、密码输入（不回显）等高级功能。
        attrs[3] &= ~termios.ICANON  # c_lflag (local flags) 索引为 3
        attrs[3] &= ~termios.ECHO      # <--- 关键修复！从 |= (开启) 变为 &= ~ (关闭)
        
        # 4. 应用修改后的设置
        termios.tcsetattr(master_fd, termios.TCSADRAIN, attrs)

        sandboxed_env = self._create_sandboxed_environment()

        self.shell_process = await asyncio.create_subprocess_exec(
            "bash", "--norc", "--noprofile",
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            env=sandboxed_env, start_new_session=True
        )

        # 注册一个文件读取器，当PTY有输出时，异步读取
        loop = asyncio.get_running_loop()
        loop.add_reader(self.pty_master_fd, self._read_from_pty)
        
        # 关闭从属端文件描述符，因为子进程已经继承了它
        os.close(slave_fd)

    def _create_sandboxed_environment(self) -> Dict[str, str]:
        """创建一个隔离的、干净的环境变量字典给子进程使用。"""
        clean_env: Dict[str, str] = {}
        for var in ESSENTIAL_VARS:
            if var in os.environ:
                clean_env[var] = os.environ[var]

        clean_env["TERM"] = "xterm-256color"  # 声明终端类型，以便彩色输出
        clean_env["PS1"] = SHELL_PROMPT
        return clean_env

    def _read_from_pty(self) -> None:
        """从PTY主设备读取数据并写入到日志组件中。"""
        try:
            # 读取最多1024字节的数据
            data = os.read(self.pty_master_fd, 1024)
            if data:
                # 使用Text.from_ansi来解析包含ANSI转义码的文本（如颜色）
                rich_text = Text.from_ansi(data.decode('utf-8', errors='replace'))
                # 写入日志，append=True确保内容被追加，而不是替换
                # RichLog的write默认行为就是追加，并且正确处理换行符
                self.log_widget.write(rich_text)
        except OSError:
            # 当进程关闭时，读取可能会失败，这是正常的
            pass
            
    async def on_key(self, event: Key) -> None:
        """
        *** 核心修复点 2: 完整处理按键事件 ***
        捕获Textual的按键事件，并将其转发给Shell进程。
        """
        if self.pty_master_fd is not None:
            # 处理回车键
            if event.key == "enter":
                os.write(self.pty_master_fd, b'\r')
            # 处理退格键
            elif event.key == "backspace":
                # 发送 ASCII DEL 字符 (127)，这是终端中常见的退格码
                os.write(self.pty_master_fd, b'\x7f')
            # 处理其他可打印字符
            elif event.character:
                os.write(self.pty_master_fd, event.character.encode('utf-8'))


    async def action_quit(self) -> None:
        """优雅地关闭应用、Shell进程和PTY。"""
        if self.pty_master_fd:
            # 停止监听PTY
            asyncio.get_running_loop().remove_reader(self.pty_master_fd)
            
            # ！！！至关重要：恢复原始终端设置！！！
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