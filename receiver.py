from tmux_cmd_runner import TmuxTerminal, CommandResult

# def send_keys(keys: str, term: TmuxTerminal):
#     term._pane.send_keys(keys)

# def send_keys_batch(keys_list: list | tuple, term: TmuxTerminal):
#     for keys in keys_list:
#         term._pane.send_keys(keys)

with TmuxTerminal(session_name="hello") as term:
    term.execute(
        [
            "seq 10"
        ]
    )
    print(CommandResult.get())
