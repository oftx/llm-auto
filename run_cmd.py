import subprocess
import platform
import threading
import os
import shutil
from typing import Optional, List

class CommandExecutor:
    """
    一个可复用的、面向对象的命令执行器。
    
    通过 `reset()` 方法为新命令重置状态，以避免在批量操作中
    重复创建对象的开销。
    """
    def __init__(self, encoding: str = 'utf-8'):
        self.encoding = encoding
        self.command_string: Optional[str] = None
        self.cwd: Optional[str] = None
        self.shell: bool = True
        self._result: Optional[subprocess.CompletedProcess] = None
        self._executed = False

    def reset(self, command_string: str, cwd: Optional[str], shell: bool = True) -> 'CommandExecutor':
        """用新命令的配置重置执行器。"""
        self.command_string = command_string
        self.cwd = cwd
        self.shell = shell
        self._result = None
        self._executed = False
        return self

    def run(self, stream_output: bool = False) -> 'CommandExecutor':
        """执行已配置的命令。"""
        if not self.command_string:
            raise RuntimeError("Executor not configured. Call reset() before run().")
        
        try:
            if stream_output:
                self._run_streaming()
            else:
                self._run_blocking()
        except FileNotFoundError:
            stderr = f"Command not found: {self.command_string.split()[0]}"
            self._result = subprocess.CompletedProcess(self.command_string, -1, stderr=stderr)
        except Exception as e:
            self._result = subprocess.CompletedProcess(self.command_string, -2, stderr=str(e))
        
        self._executed = True
        return self

    def _stream_reader(self, stream, output_lines: list, prefix: str):
        """实时读取流并存储输出。"""
        for line in iter(stream.readline, ''):
            print(f"{prefix} {line.strip()}", flush=True)
            output_lines.append(line)
        stream.close()

    def _run_streaming(self):
        """以流式方式执行命令，实时打印输出。"""
        process = subprocess.Popen(
            self.command_string, shell=self.shell, stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, text=True, encoding=self.encoding, cwd=self.cwd
        )
        stdout_lines, stderr_lines = [], []
        thread_stdout = threading.Thread(target=self._stream_reader, args=(process.stdout, stdout_lines, "[stdout]"))
        thread_stderr = threading.Thread(target=self._stream_reader, args=(process.stderr, stderr_lines, "[stderr]"))
        
        thread_stdout.start()
        thread_stderr.start()
        thread_stdout.join()
        thread_stderr.join()
        process.wait()

        self._result = subprocess.CompletedProcess(
            process.args, process.returncode,
            stdout="".join(stdout_lines), stderr="".join(stderr_lines)
        )

    def _run_blocking(self):
        """以阻塞方式执行命令，一次性获取所有输出。"""
        self._result = subprocess.run(
            self.command_string, shell=self.shell, capture_output=True,
            text=True, encoding=self.encoding, cwd=self.cwd
        )

    def _check_if_executed(self):
        if not self._executed:
            raise RuntimeError("Command has not been executed yet. Call run() first.")

    @property
    def returncode(self) -> int:
        self._check_if_executed()
        return self._result.returncode

    @property
    def stdout(self) -> str:
        self._check_if_executed()
        return self._result.stdout

    @property
    def stderr(self) -> str:
        self._check_if_executed()
        return self._result.stderr

    @property
    def success(self) -> bool:
        self._check_if_executed()
        return self.returncode == 0

class TerminalSession:
    """
    模拟一个带状态的终端会话，支持交互式、单个及批量命令执行。
    
    通过持有一个可复用的 `CommandExecutor` 实例来优化批量任务性能。
    """
    def __init__(self, start_dir: Optional[str] = None):
        self.cwd = os.path.abspath(start_dir or os.getcwd())
        self._executor = CommandExecutor()
        print(f"终端会话已启动，当前目录: {self.cwd}")

    @property
    def prompt(self) -> str:
        """生成一个类似终端的提示符。"""
        display_path = self.cwd
        if platform.system() != "Windows":
            home_dir = os.path.expanduser("~")
            if self.cwd.startswith(home_dir):
                display_path = f"~{self.cwd[len(home_dir):]}"
        return f"{display_path} $ "
        
    def _handle_cd(self, target_dir: str) -> bool:
        """内部处理 'cd' 命令，改变会话的当前工作目录。"""
        if not target_dir or target_dir == '~':
            target_dir = os.path.expanduser('~')
        elif target_dir.startswith('~/'):
            target_dir = os.path.expanduser(target_dir)

        new_path = os.path.abspath(os.path.join(self.cwd, target_dir))
        
        if os.path.isdir(new_path):
            self.cwd = new_path
            return True

        original_target = target_dir if target_dir else "home directory"
        print(f"cd: no such file or directory: {original_target}")
        return False

    def execute(self, command_string: str, stream_output: bool = True, verbose: bool = True) -> bool:
        """
        在当前会话中执行单个命令。
        
        特殊处理 'cd' 命令，其余命令委托给内部执行器。
        返回命令是否成功。
        """
        command_string = command_string.strip()
        if not command_string: return True
        if verbose: print(f"--- [执行]: {command_string} ---")
        
        if command_string.startswith("cd "):
            success = self._handle_cd(command_string[3:].strip())
        elif command_string.lower() == 'pwd':
            print(self.cwd)
            success = True
        else:
            self._executor.reset(command_string, self.cwd).run(stream_output)
            success = self._executor.success
            if not success and not stream_output and self._executor.stderr:
                print(self._executor.stderr.strip())

        if verbose: print(f"--- [结束 (成功: {success})] ---")
        return success

    def execute_batch(self, commands: List[str], stream_output: bool = False, verbose: bool = True) -> bool:
        """
        按顺序执行命令列表，任何命令失败则立即中断。
        
        :param commands: 要执行的命令字符串列表。
        :param stream_output: 是否实时打印每个子命令的输出。
        :param verbose: 是否打印详细的步骤信息和最终摘要。
        :return: 所有命令是否都成功执行。
        """
        if verbose: print(f"\n--- [开始批量执行 {len(commands)} 条命令] ---")
        
        for i, command in enumerate(commands):
            if verbose: print(f"\n[步骤 {i+1}/{len(commands)}] > {command}")
            
            success = self.execute(command, stream_output, verbose=False)
            
            if not success:
                print(f"\n[!!] 批量执行失败于步骤 {i+1}: '{command}'")
                if self._executor._executed and self._executor.stderr:
                    print("错误详情:", self._executor.stderr.strip())
                print("--- [批量执行已终止] ---")
                return False
        
        if verbose: print("\n--- [批量执行成功] 所有命令均已成功。 ---")
        return True

    def run_interactive(self):
        """启动一个交互式循环，模拟真实终端。"""
        while True:
            try:
                command = input(self.prompt)
                if command.lower() in ["exit", "quit"]: break
                self.execute(command)
            except KeyboardInterrupt:
                print() # 换行
                break
        print("终端会话结束。")

if __name__ == "__main__":
    session = TerminalSession()
    session.execute("sudo ls .")