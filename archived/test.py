import re

def _word_to_regex(word: str) -> str:
    """
    将一个单词转换为一个正则表达式模式，该模式允许字符之间存在任意的空白（包括换行符）。
    """
    return r'\s*'.join(re.escape(c) for c in word)

def clean_output(lines_iter: list[str]) -> str:
    """
    清理Linux终端运行结果字符串，移除特定的标记命令及其输出。
    此最终版本使用“回溯引用”策略，在确保安全性的同时，精确保留真实命令的输出。

    Args:
        lines_iter: 一个包含终端输出各行的列表。

    Returns:
        一个清理后的、单一的字符串。
    """
    if not lines_iter:
        return ""

    full_output = '\n'.join(lines_iter)

    # 定义标记命令的模式
    command_part = (
        r';'
        r'\s*' + _word_to_regex('echo') + r'\s*'
        r'"\s*' + _word_to_regex('TMUX_CMD_EXIT_CODE_') + r'.*?'
        + re.escape(':$?') +
        r'"'
        r'\s*;\s*'
        r'\s*' + _word_to_regex('tmux') + r'\s*'
        r'\s*' + _word_to_regex('wait-for') + r'\s*'
        r'-S\s*".*?"'
    )

    # 定义标记输出的模式 (必须在行首)
    output_part = (
        r'^\s*'
        + _word_to_regex('TMUX_CMD_EXIT_CODE_')
        + r'.*?'
        + r':'
        + r'[\s\d]*'
    )

    # 构建原子块模式，包含三个捕获组
    atomic_block_pattern = re.compile(
        f"({command_part})"  # 组 1: 标记命令
        f"(.*?)"             # 组 2: 真实输出 (我们想保留的内容)
        f"({output_part})",  # 组 3: 标记输出
        re.DOTALL | re.MULTILINE
    )

    # 关键：使用回溯引用 r'\2' 替换整个区块，从而只保留真实输出
    cleaned_text = atomic_block_pattern.sub(r'\2', full_output)
    
    return cleaned_text.strip()


# --- 最终的、经过修正的综合测试用例 ---
# 注意：Test Case 3 的预期结果已被修正，以匹配正确的输出
test_cases = [
    ("Test Case 1: Empty Input", [], ""),
    ("Test Case 2: No Marker Command", ['➜  Downloads ls -l', 'total 0', '➜  Downloads'], '➜  Downloads ls -l\ntotal 0\n➜  Downloads'),
    # 关键修正：修复了预期输出中的笔误 (现在是正确的40个'a')
    ("Test Case 3: Standard Case (from prompt)", ['➜  Downloads echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;echo "TMUX_CMD_EXIT_CODE_0:$?";tmux wait-for -S "tmux-wait-0"', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'TMUX_CMD_EXIT_CODE_0:0', '➜  Downloads'], '➜  Downloads echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\naaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n➜  Downloads'),
    ("Test Case 4: Extreme Wrapping (Command & Output)", ['➜  Downloads echo bbb;e', 'cho "TMUX_CMD_EXIT_CODE_127:$?";t', 'mux wait-for -S "tmux-w', 'ait-id-123"', 'bbb', 'TMUX_CMD_EXIT_CODE_127', ':127', '➜  Downloads '], '➜  Downloads echo bbb\nbbb\n➜  Downloads'),
    ("Test Case 5: Simulation of a Very Narrow Terminal", ['➜ echo hi;ec', 'ho "TMUX_CMD', '_EXIT_CODE_0', ':$?";tmux w', 'ait-for -S ', '"id-0"', 'hi', 'TMUX_CMD_EXI', 'T_CODE_0:0', '➜ '], '➜ echo hi\nhi\n➜'),
    ("Test Case 6: Multiple Markers in One Output", ['➜ echo 1;echo "TMUX_CMD_EXIT_CODE_0:$?";tmux wait-for -S "id-0"', '1', 'TMUX_CMD_EXIT_CODE_0:0', '➜ echo 2;echo "TMUX_CMD_EXIT_CODE_1:$?";tmux wait-for -S "id-1"', '2', 'TMUX_CMD_EXIT_CODE_1:1', '➜ '], '➜ echo 1\n1\n➜ echo 2\n2\n➜'),
    ("Test Case 7: Only Marker in the Entire Output", [';echo "TMUX_CMD_EXIT_CODE_0:$?";tmux wait-for -S "id-0"', 'TMUX_CMD_EXIT_CODE_0:0'], ""),
    ("Test Case 8: Extra Whitespace and Tabs", ['➜ echo cmd; \t echo "TMUX_CMD_EXIT_CODE_0:$?";\t tmux \t wait-for    -S "id-0"', 'cmd', 'TMUX_CMD_EXIT_CODE_0:0', '➜ '], '➜ echo cmd\ncmd\n➜'),
    ("Test Case 9: CRITICAL - False Positive Test", ['➜  Downloads echo "A user string: TMUX_CMD_EXIT_CODE_99:99"', 'A user string: TMUX_CMD_EXIT_CODE_99:99', '➜  Downloads'], '➜  Downloads echo "A user string: TMUX_CMD_EXIT_CODE_99:99"\nA user string: TMUX_CMD_EXIT_CODE_99:99\n➜  Downloads'),
    ("Test Case 10: Real Command Output Contains Newlines", ['➜ ls -l;echo "TMUX_CMD_EXIT_CODE_0:$?";tmux wait-for -S "id-0"', 'total 8', '-rw-r--r--  1 user  staff  123 Jul 30 10:00 file1', 'TMUX_CMD_EXIT_CODE_0:0', '➜ '], '➜ ls -l\ntotal 8\n-rw-r--r--  1 user  staff  123 Jul 30 10:00 file1\n➜'),
    ("Test Case 11: Realistic 'No Newline' Scenario", ['➜ echo hi;echo "TMUX_CMD_EXIT_CODE_0:$?";tmux wait-for -S "id-0"', 'hi', 'TMUX_CMD_EXIT_CODE_0:0', '➜ '], '➜ echo hi\nhi\n➜')
]

# --- 运行所有测试 ---
all_passed = True
for name, lines, expected in test_cases:
    actual = clean_output(lines)
    if actual.strip().splitlines() == expected.strip().splitlines():
        pass
    else:
        all_passed = False
        print(f"--- Running: {name} ---")
        print(f"❌ FAILED")
        print(f"  Input:\n{lines}")
        print(f"  Expected:\n---\n{expected.strip()}\n---")
        print(f"  Actual:\n---\n{actual}\n---")
        print()

print("="*40)
if all_passed:
    print("🎉 All test cases passed successfully!")
else:
    print("🔥 Some test cases failed.")