from tmux_cmd_runner import TmuxTerminal, CommandResult

with TmuxTerminal(session_name="hello") as term:
    term.execute(
        [
            "date"
        ]
    )
    print(CommandResult.get())
