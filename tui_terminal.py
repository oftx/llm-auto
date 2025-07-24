import asyncio
import os
import pty
import shlex
from typing import Dict, List

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, RichLog, Input
from textual.containers import Container

# --- Configuration Constants ---

# A minimal set of environment variables essential for a functional shell.
# This "whitelist" approach creates a secure and predictable execution environment.
ESSENTIAL_VARS: List[str] = [
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE"
]

# A simple, clean, and informative prompt format for our shell.
# Format: [bold green]~/your/path[/] $
SHELL_PROMPT: str = r"\[\033[01;32m\]\w\[\033[00m\] \$ "


class TerminalApp(App):
    """
    A robust, embedded TUI terminal that runs a clean, isolated shell session.
    It creates a hermetically sealed environment to ensure predictable behavior
    across different user systems.
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]
    CSS_PATH = "tui_terminal.css"

    def __init__(self):
        super().__init__()
        self.shell_process: asyncio.subprocess.Process | None = None
        self.pty_master_fd: int | None = None
        self.log_widget = RichLog(id="log", highlight=True, markup=True, wrap=True)

    def compose(self) -> ComposeResult:
        """Create the layout and widgets for the application."""
        yield Header()
        with Container(id="app-grid"):
            yield self.log_widget
            yield Input(placeholder="Enter a command...", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted. Starts the PTY and shell process."""
        self.log_widget.write("[b]Initializing clean-room PTY shell session...[/b]")
        await self._start_shell_in_pty()
        self.query_one(Input).focus()

    async def _start_shell_in_pty(self):
        """Creates a PTY and launches a sandboxed bash shell within it."""
        master_fd, slave_fd = pty.openpty()
        self.pty_master_fd = master_fd

        sandboxed_env = self._create_sandboxed_environment()

        self.shell_process = await asyncio.create_subprocess_exec(
            "bash", "--norc", "--noprofile",
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=sandboxed_env
        )

        loop = asyncio.get_running_loop()
        loop.add_reader(self.pty_master_fd, self._read_from_pty)

    def _create_sandboxed_environment(self) -> Dict[str, str]:
        """
        Constructs a minimal, whitelisted "clean room" environment.
        This prevents interference from the parent shell's configuration.
        """
        clean_env: Dict[str, str] = {}
        for var in ESSENTIAL_VARS:
            if var in os.environ:
                clean_env[var] = os.environ[var]

        clean_env["TERM"] = "xterm-256color"
        clean_env["PS1"] = SHELL_PROMPT
        return clean_env

    def _read_from_pty(self) -> None:
        """Callback to read data from the shell process via the PTY."""
        try:
            # The PTY gives us raw bytes; we decode and convert to Rich Text.
            data = os.read(self.pty_master_fd, 1024)
            if data:
                rich_text = Text.from_ansi(data.decode('utf-8', errors='replace'))
                self.log_widget.write(rich_text, scroll_end=True)
        except OSError:
            # This can happen when the PTY is closed.
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handles user command input."""
        command = event.value
        input_widget = self.query_one("#input", Input)
        input_widget.value = ""

        if not command.strip():
            return

        if self.pty_master_fd is not None:
            os.write(self.pty_master_fd, f"{command}\n".encode('utf-8'))
            self._handle_built_in_commands(command)

    def _handle_built_in_commands(self, command: str):
        """
        Synchronizes the Python process's state for certain shell commands.
        Currently handles 'cd' to keep the working directory in sync.
        """
        try:
            if command.strip().startswith('cd '):
                parts = shlex.split(command)
                if len(parts) > 1:
                    path = os.path.expanduser(parts[1])
                    os.chdir(path)
        except (FileNotFoundError, IndexError):
            # Let the shell report the error to the user, do nothing here.
            pass

    async def action_quit(self) -> None:
        """Gracefully shuts down the application and shell process."""
        if self.pty_master_fd:
            asyncio.get_running_loop().remove_reader(self.pty_master_fd)
            os.close(self.pty_master_fd)

        if self.shell_process and self.shell_process.returncode is None:
            self.shell_process.terminate()
            await self.shell_process.wait()

        self.exit()


if __name__ == "__main__":
    if os.name != "posix":
        print("This application requires a POSIX-like OS (Linux, macOS) due to its use of the 'pty' module.")
    else:
        app = TerminalApp()
        app.run()