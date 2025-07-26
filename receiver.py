from tmux_cmd_runner import TmuxTerminal, CommandResult

with TmuxTerminal(session_name="hello") as term:
    term.execute(
        [
            "ls .",
            "cd ..",
            "ls -la"
        ]
    )
    CommandResult.save_from_terminal(terminal_instance=term)
    print(CommandResult.get())
