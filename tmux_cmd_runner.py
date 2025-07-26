import libtmux
import os
import time
from functools import singledispatch
from typing import Optional, List, Union, Tuple, Dict

class ExecutionPolicy:
    """封装命令执行成功/失败规则的策略类。"""
    def __init__(self):
        self._rules: Dict[str, List[int]] = {}
        self.default_accepted_codes = [0]

    @classmethod
    def with_common_rules(cls) -> 'ExecutionPolicy':
        policy = cls()
        policy.add_rule("grep", accepted_codes=[0, 1])
        policy.add_rule("diff", accepted_codes=[0, 1])
        return policy

    def add_rule(self, command_prefix: str, accepted_codes: List[int]):
        self._rules[command_prefix] = accepted_codes

    def get_accepted_codes(self, command_string: str) -> List[int]:
        for prefix, codes in self._rules.items():
            if command_string.strip().startswith(prefix):
                return codes
        return self.default_accepted_codes

class CommandResult:
    """一个用于管理和返回命令执行结果的静态类。"""
    last_output: Optional[str] = None

    @staticmethod
    def save_from_terminal(terminal_instance: 'TmuxTerminal'):
        output = terminal_instance.capture_clean_output()
        CommandResult.last_output = output

    @staticmethod
    def get() -> Optional[str]:
        return CommandResult.last_output

    @staticmethod
    def clear():
        CommandResult.last_output = None

@singledispatch
def _execute_dispatcher(command: Union[str, list, tuple], term_instance: 'TmuxTerminal') -> bool:
    raise TypeError(f"不支持的命令类型: {type(command)}")

@_execute_dispatcher.register(str)
def _execute_str(command_string: str, term_instance: 'TmuxTerminal') -> bool:
    pane = term_instance._pane
    if not pane: raise RuntimeError("Tmux 会话尚未初始化。")

    print(f"> {repr(command_string)}")

    channel_name = f"tmux-wait-{term_instance._command_counter}"
    exit_code_marker = f"TMUX_CMD_EXIT_CODE_{term_instance._command_counter}"
    term_instance._command_counter += 1

    pane.send_keys(command_string, enter=True)
    pane.send_keys(f'echo "{exit_code_marker}:$?"', enter=True)
    pane.send_keys(f'tmux wait-for -S "{channel_name}"', enter=True)
    
    try:
        term_instance._server.cmd('wait-for', channel_name)
    except Exception as e:
        print(f"[!!] 等待命令 '{command_string}' 完成时出错: {e}")
        return False

    time.sleep(0.1)
    output_lines = pane.capture_pane()
    
    exit_code = -1
    for line in reversed(output_lines):
        if line.strip().startswith(exit_code_marker):
            try:
                exit_code = int(line.strip().split(':')[1])
                break
            except (IndexError, ValueError): continue
    
    if exit_code == -1:
        print(f"[!!] 无法确定命令 '{command_string}' 的退出状态码。")
        return False

    accepted_codes = term_instance.policy.get_accepted_codes(command_string)
    
    if exit_code in accepted_codes:
        return True
    else:
        print(f"[⚠️] 命令 '{command_string}' 返回了非预期退出码: {exit_code}")
        choice = input("    检测到命令可能执行失败，是否继续执行？(y/N): ").lower().strip()
        if choice == 'y':
            print("    用户选择继续执行。")
            return True
        else:
            print("    用户选择中止。")
            return False

@_execute_dispatcher.register(list)
@_execute_dispatcher.register(tuple)
def _execute_list(command_list: Union[List[str], Tuple[str]], term_instance: 'TmuxTerminal') -> bool:
    for command in command_list:
        if not isinstance(command, str):
            print(f"[!!] 命令列表中的项目必须是字符串，但收到了 {type(command)}。正在跳过。")
            continue
        
        success = _execute_dispatcher(command, term_instance)
        
        if not success:
            print(f"\n[!!] 由于上一条命令失败或用户中止，正在停止后续命令的执行。")
            return False
    return True

class TmuxTerminal:
    """一个使用策略驱动的、用于顺序执行命令的 tmux 会话管理器。"""
    def __init__(self, session_name: str, start_dir: Optional[str] = None, policy: Optional[ExecutionPolicy] = None):
        self.session_name = session_name
        self.start_dir = os.path.abspath(start_dir or os.getcwd())
        self._server = libtmux.Server()
        self._session: Optional[libtmux.Session] = None
        self._pane: Optional[libtmux.Pane] = None
        self._command_counter = 0
        self.policy = policy or ExecutionPolicy()

    def __enter__(self):
        self._session = self._server.find_where({"session_name": self.session_name})
        if self._session:
            print(f"已连接到现有 Tmux 会话 '{self.session_name}'...")
        else:
            print(f"正在创建 Tmux 会话 '{self.session_name}'...")
            self._session = self._server.new_session(session_name=self.session_name)
        
        self._pane = self._session.active_window.active_pane
        print(f"会话 '{self.session_name}' 已准备就绪。")
        print(f"✨ 可在新终端使用以下命令连接会话: tmux attach -t {self.session_name}")
        return self
    
    def capture_clean_output(self) -> str:
        """捕获 tmux 窗格的当前内容，并清理掉所有内部使用的标记。"""
        if not self._pane:
            return "[!!] 错误：无法捕获输出，因为 tmux 窗格不可用。"

        full_output: List[str] = self._pane.capture_pane()
        
        clean_lines = [
            line for line in full_output 
            if 'tmux wait-for -S' not in line and 'TMUX_CMD_EXIT_CODE_' not in line
        ]
        
        final_output_lines = []
        for i, line in enumerate(clean_lines):
            if i > 0 and not line.strip() and not clean_lines[i-1].strip():
                continue
            final_output_lines.append(line)
        
        return '\n'.join(final_output_lines).strip()

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("\n----------------------------------------")
        print("所有命令已执行完毕或被中止")
        print("----------------------------------------")
        choice = input("是否需要关闭此 Tmux 会话？(y/N): ").lower().strip()
        if choice == 'y':
            print(f"正在关闭 Tmux 会话 '{self.session_name}'...")
            if self._server.has_session(self.session_name): self._server.kill_session(self.session_name)
            print("会话已关闭。")
        else:
            print(f"\n脚本已结束，Tmux 会话 '{self.session_name}' 仍在后台运行。")

    def execute(self, command: Union[str, List[str]]):
        if self._pane: self._pane.clear()
        _execute_dispatcher(command, self)

def print_result_block(title: str, result_provider):
    print("\n" + "="*20 + f" {title} " + "="*20)
    result = result_provider()
    if result:
        print(result)
    else:
        print("(无输出)")
    print("="* (42 + len(title)))

if __name__ == "__main__":
    try:
        policy = ExecutionPolicy.with_common_rules()

        with TmuxTerminal(session_name="production-demo", policy=policy) as term:
            
            # --- 测试用例 1: 简单的单行命令 ---
            term.execute("echo 'Hello\n from a single command!'")
            CommandResult.save_from_terminal(term)
            print_result_block("测试用例 1: 简单命令", CommandResult.get)

            # --- 测试用例 2: 包含换行符的多行命令 ---
            multiline_command = "for i in {1..3}; do echo \"Loop iteration $i\"; done"
            term.execute(multiline_command)
            CommandResult.save_from_terminal(term)
            print_result_block("测试用例 2: 多行命令", CommandResult.get)

            # --- 测试用例 3: 使用策略处理 'grep' ---
            term.execute([
                "echo 'unique content' > test_file.txt",
                "grep 'non_existent' test_file.txt" # 返回 1, 但被策略接受
            ])
            CommandResult.save_from_terminal(term)
            print_result_block("测试用例 3: Grep 策略 (预期无输出)", CommandResult.get)

            # --- 测试用例 4: 真正的失败与交互式处理 ---
            print("\n>>> 下一个测试将触发交互式失败提示，请做好准备...")
            term.execute("ls /non_existent_directory_for_sure")
            CommandResult.save_from_terminal(term)
            print_result_block("测试用例 4: 交互式失败", CommandResult.get)
            
            # --- 清理 ---
            term.execute("rm test_file.txt")

    except FileNotFoundError:
        print("\n[!!] 致命错误: 'tmux' 命令未找到。请确保 tmux 已安装并位于您的 PATH 中。")
    except Exception as e:
        print(f"\n[!!] 发生未处理的异常: {e}")