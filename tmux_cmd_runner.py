import libtmux
import os
import time
from functools import singledispatch
from typing import Optional, List, Union, Tuple, Dict

class ExecutionPolicy:
    """一个封装了命令执行成功/失败规则的静态策略类。"""
    _rules: Dict[str, List[int]] = {
        "grep": [0, 1],
        "diff": [0, 1]
    }
    default_accepted_codes: List[int] = [0]

    @classmethod
    def add_rule(cls, command_prefix: str, accepted_codes: List[int]):
        """为以特定前缀开头的命令添加一条全局规则。"""
        cls._rules[command_prefix] = accepted_codes

    @classmethod
    def get_accepted_codes(cls, command_string: str) -> List[int]:
        """根据给定的命令字符串，获取其可接受的退出码列表。"""
        for prefix, codes in cls._rules.items():
            if command_string.strip().startswith(prefix):
                return codes
        return cls.default_accepted_codes

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

    # 等待提示符准备就绪
    def wait_for_prompt_ready(max_attempts=10, wait_interval=0.2):
        """等待终端提示符准备就绪"""
        for attempt in range(max_attempts):
            time.sleep(wait_interval)
            output_lines = pane.capture_pane()
            if output_lines:
                last_line = output_lines[-1].strip()
                # 检查最后一行是否看起来像提示符（包含常见的提示符字符）
                if any(char in last_line for char in ['$', '>', '➜', '#', '%']) and len(last_line) > 0:
                    # 再等待一小段时间确保提示符完全加载
                    time.sleep(0.1)
                    return True
        return False

    # 等待提示符准备
    if not wait_for_prompt_ready():
        print(f"[⚠️] 警告: 提示符可能未完全加载，继续执行命令...")

    channel_name = f"tmux-wait-{term_instance._command_counter}"
    exit_code_marker = f"TMUX_CMD_EXIT_CODE_{term_instance._command_counter}"
    term_instance._command_counter += 1

    full_command = f"{command_string};echo \"{exit_code_marker}:$?\";tmux wait-for -S \"{channel_name}\""
    pane.send_keys(full_command, enter=True)
    
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
        print(f"[⚠️] 无法确定命令 '{command_string}' 的退出状态码。")
        choice = input("    请检查 tmux 会话的实际运行情况，并决定是否继续执行？(y/N): ").lower().strip()
        if choice == 'y':
            print("    用户选择继续执行。")
            return True
        else:
            print("    用户选择中止。")
            return False

    accepted_codes = ExecutionPolicy.get_accepted_codes(command_string)
    
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
    """一个使用全局策略驱动的、用于顺序执行命令的 tmux 会话管理器。"""
    def __init__(self, session_name: str, start_dir: Optional[str] = None):
        self.session_name = session_name
        self.is_running_cmd = False
        self.start_dir = os.path.abspath(start_dir or os.getcwd())
        self._server = libtmux.Server()
        self._session: Optional[libtmux.Session] = None
        self._pane: Optional[libtmux.Pane] = None
        self._command_counter = 0

    def __enter__(self):
        sessions = self._server.sessions.filter(session_name=self.session_name)
        self._session = next(iter(sessions), None)
        if self._session:
            print(f"已连接到现有 Tmux 会话 '{self.session_name}'...")
        else:
            self._session = self._server.new_session(session_name=self.session_name)
            print(f"已创建 Tmux 会话 '{self.session_name}'...")
        
        history_limit = 50000
        self._session.set_option('history-limit', history_limit) 
        
        self._pane = self._session.active_window.active_pane
        
        time.sleep(0.5)
        
        print(f"✨ 可在新终端使用以下命令连接会话: tmux attach -t {self.session_name}")
        return self
    
    def capture_clean_output(self) -> str:
        """
        捕获并清理窗格输出，专门处理因命令过长而换行导致的残留问题。
        """
        if not self._pane: return "[!!] 错误：无法捕获输出，因为 tmux 窗格不可用。"
        full_output: List[str] = self._pane.cmd("capture-pane", "-p", "-S-", "-E-").stdout

        processed_lines = []
        lines_iter = iter(full_output) # 使用迭代器以便可以消耗后续行

        for line in lines_iter:
            # 我们注入的命令的特征标记
            junk_marker = ';echo "TMUX_CMD_EXIT_CODE_'
            
            # 情况1: 当前行是纯粹的退出码报告行 (例如, "TMUX_CMD_EXIT_CODE_0:0")，直接跳过。
            if line.strip().startswith("TMUX_CMD_EXIT_CODE_") and ":" in line:
                continue
            
            # 情况2: 当前行包含了用户命令和我们注入的“脚手架”命令。
            if junk_marker in line:
                # 通过标记分割字符串，只保留我们需要的用户命令部分。
                clean_line = line.split(junk_marker)[0]
                processed_lines.append(clean_line)
                
                # 检查注入的命令是否在当前行就已完整结束。
                # 完整的注入命令以一个双引号 `"` 结尾。
                if 'tmux wait-for -S' in line and line.rstrip().endswith('"'):
                    # 如果是，则无需进一步处理，继续下一个循环。
                    pass
                else:
                    # 如果不是，说明命令已换行，我们需要消耗并丢弃后续的残留行。
                    # 持续消耗迭代器中的行，直到找到包含结束双引号 `"` 的那一行。
                    for next_line in lines_iter:
                        if '"' in next_line:
                            break # 找到了残留的最后一部分，跳出内层循环。
                
                # 跳过当前行的剩余部分，继续外层循环。
                continue
                
            # 情况3: 当前行是正常的命令输出，直接保留。
            processed_lines.append(line)
        
        # 对清理后的行进行最终处理，移除可能产生的连续空行。
        final_output_lines = []
        for i, line in enumerate(processed_lines):
            if i > 0 and not line.strip() and not processed_lines[i-1].strip():
                continue
            final_output_lines.append(line)
        
        return '\n'.join(final_output_lines).strip()


    def __exit__(self, exc_type, exc_val, exc_tb):
        choice = input("运行完成，是否需要关闭此 Tmux 会话？(y/N): ").lower().strip()
        if choice == 'y':
            print(f"正在关闭 Tmux 会话 '{self.session_name}'...")
            if self._server.has_session(self.session_name): self._server.kill_session(self.session_name)
            print("会话已关闭。")
        else:
            print(f"脚本已结束，Tmux 会话 '{self.session_name}' 仍在后台运行（如果未退出）。")

    def execute(self, command: Union[str, List[str]]):
        if self.is_running_cmd:
            print("正在运行中，请稍后传入命令")
            return
        self.is_running_cmd = True
        if self._pane:
            self._pane.clear()
            self._pane.cmd('clear-history')
            time.sleep(0.2)
        try:
            _execute_dispatcher(command, self)
            CommandResult.save_from_terminal(self)
        finally:
            self.is_running_cmd = False

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
        with TmuxTerminal(session_name="hello") as term:
            term.execute("date")
            print_result_block("日期命令测试", CommandResult.get)

    except FileNotFoundError:
        print("\n[!!] 致命错误: 'tmux' 命令未找到。请确保 tmux 已安装并位于您的 PATH 中。")