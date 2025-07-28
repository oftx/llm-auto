from typing import List, Union
from tmux_cmd_runner import TmuxTerminal, CommandResult

with TmuxTerminal(session_name="cmd-runner") as term:
    def run_cmd(cmd: Union[str, List[str]]) -> None:
        """
        Execute a command in a Tmux terminal.

        Args:
            cmd: A string or list of strings representing the command(s) to execute.

        Raises:
            TypeError: If cmd is neither a string nor a list of strings.
            ValueError: If cmd is an empty string or empty list.
        """
        if not isinstance(cmd, (str, list)):
            raise TypeError(f"Unsupported parameter type: {type(cmd)}. Expected str or list.")

        if isinstance(cmd, str) and not cmd.strip():
            raise ValueError("Command string cannot be empty.")

        if isinstance(cmd, list) and not cmd:
            raise ValueError("Command list cannot be empty.")

        try:
            term.execute(cmd)
        except Exception as e:
            raise RuntimeError(f"Failed to execute command: {e}") from e
    
    try:
        run_cmd("ls .")
        print(CommandResult.get())
    except Exception as e:
        print(e)
