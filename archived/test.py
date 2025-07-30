def clean_output(lines_iter):
    processed_lines = []
    junk_marker = ';echo "TMUX_CMD_EXIT_CODE_'

    for line in lines_iter:
        if line.strip().startswith("TMUX_CMD_EXIT_CODE_") and ":" in line:
            continue

        if junk_marker in line:
            clean_line = line.split(junk_marker)[0]
            processed_lines.append(clean_line)

            if 'tmux wait-for -S' in line:
                try:
                    for next_line in lines_iter:
                        if 'tmux-wait-' in next_line:
                            break
                except StopIteration:
                    pass
            continue

        processed_lines.append(line)

    final_output_lines = []
    for i, line in enumerate(processed_lines):
        stripped_line = line.strip()
        if i > 0 and not stripped_line and not processed_lines[i-1].strip():
            continue
        final_output_lines.append(line)

    return '\n'.join(final_output_lines).rstrip()

# 示例用法
lines = [
    '((.venv) ) ➜  llm-auto git:(main) ✗ python archived/test.py',
    '➜  Downloads date;e'
    'c'
    'ho "TMUX_C'
    'MD_EX'
    'IT'
    '_CODE_0:$?";tmux'
    ' wait-f'
    'or -S "',
    't'
    'm'
    'u'
    'x'
    '-'
    'w'
    'a'
    'it-0"',
    '2025年 7月30日 星期三 16时50分09秒 CST',
    'TMUX_CMD_EXIT_CODE_0:0',
    '➜  Downloads'
]
lines_iter = iter(lines)
print(clean_output(lines_iter))