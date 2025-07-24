import subprocess
import platform
import threading
import os
import time
from typing import Optional, List

class CommandExecutor:
    """
    一个可复用的、面向对象的命令执行器。
    它现在可以通过 reset() 方法来准备执行新命令，而无需重新创建实例。
    """
    def __init__(self, encoding: str = 'utf-8'):
        """
        初始化时不再需要 command_string 或 cwd。
        这些状态将在每次执行前通过 reset() 设置。
        """
        self.encoding = encoding
        self.command_string: Optional[str] = None
        self.cwd: Optional[str] = None
        self.shell: bool = True
        
        self._result: Optional[subprocess.CompletedProcess] = None
        self._executed = False

    def reset(self, command_string: str, cwd: Optional[str], shell: bool = True) -> 'CommandExecutor':
        """
        重置执行器的状态以准备一个新命令。这是性能优化的核心。
        """
        self.command_string = command_string
        self.cwd = cwd
        self.shell = shell
        self._result = None
        self._executed = False
        return self # 支持链式调用

    def run(self, stream_output: bool = False) -> 'CommandExecutor':
        if not self.command_string:
            raise RuntimeError("执行器未配置命令。请在使用 run() 前先调用 reset()。")
            
        try:
            if stream_output: self._run_streaming()
            else: self._run_blocking()
        except FileNotFoundError:
            self._result = subprocess.CompletedProcess(args=self.command_string, returncode=-1, stdout="", stderr=f"命令未找到: {self.command_string.split()[0]}")
        except Exception as e:
            self._result = subprocess.CompletedProcess(args=self.command_string, returncode=-2, stdout="", stderr=str(e))
        
        self._executed = True
        return self

    def _stream_reader(self, stream, output_lines: List[str], prefix: str, print_stream: bool):
        for line in iter(stream.readline, ''):
            if print_stream:
                print(f"{prefix} {line.strip()}", flush=True)
            output_lines.append(line)
        stream.close()

    def _run_streaming(self):
        process = subprocess.Popen(
            self.command_string, shell=self.shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding=self.encoding, cwd=self.cwd
        )
        stdout_lines, stderr_lines = [], []
        thread_stdout = threading.Thread(target=self._stream_reader, args=(process.stdout, stdout_lines, "[stdout]", True))
        thread_stderr = threading.Thread(target=self._stream_reader, args=(process.stderr, stderr_lines, "[stderr]", True))
        thread_stdout.start()
        thread_stderr.start()
        thread_stdout.join()
        thread_stderr.join()
        process.wait()
        self._result = subprocess.CompletedProcess(
            args=self.command_string, returncode=process.returncode,
            stdout="".join(stdout_lines), stderr="".join(stderr_lines)
        )

    def _run_blocking(self):
        self._result = subprocess.run(
            self.command_string, shell=self.shell, capture_output=True,
            text=True, encoding=self.encoding, cwd=self.cwd
        )
    def _check_if_executed(self):
        if not self._executed: raise RuntimeError("命令尚未执行，请先调用 .run() 方法。")
    @property
    def returncode(self) -> int:
        self._check_if_executed(); return self._result.returncode
    @property
    def stdout(self) -> str:
        self._check_if_executed(); return self._result.stdout
    @property
    def stderr(self) -> str:
        self._check_if_executed(); return self._result.stderr
    @property
    def success(self) -> bool:
        self._check_if_executed(); return self.returncode == 0

class TerminalSession:
    """
    模拟一个终端会话，现在持有一个可复用的 CommandExecutor 实例以提升批量处理性能。
    """
    def __init__(self, start_dir: Optional[str] = None):
        """
        初始化时，创建一个可复用的 CommandExecutor 实例。
        """
        self.cwd = os.path.abspath(start_dir or os.getcwd())
        self._executor = CommandExecutor() # <<< 核心变化：创建并持有实例
        print(f"终端会话已启动，当前目录: {self.cwd}")

    @property
    def prompt(self) -> str:
        display_path = self.cwd
        if platform.system() != "Windows":
            home_dir = os.path.expanduser("~")
            if self.cwd.startswith(home_dir):
                display_path = "~" + self.cwd[len(home_dir):]
        return f"{display_path} $ "
        
    def _handle_cd(self, target_dir: str) -> bool:
        new_path = os.path.abspath(os.path.join(self.cwd, target_dir))
        if os.path.isdir(new_path):
            self.cwd = new_path
            return True
        else:
            print(f"cd: no such file or directory: {target_dir}")
            return False

    def execute(self, command_string: str, stream_output: bool = True, verbose: bool = True) -> bool:
        """
        执行单个命令。现在使用 self._executor 并通过 reset() 复用它。
        """
        command_string = command_string.strip()
        if not command_string: return True
        if verbose: print(f"--- [执行]: {command_string} ---")
        
        if command_string.startswith("cd "):
            target_dir = command_string[3:].strip()
            success = self._handle_cd(target_dir)
        else:
            self._executor.reset(command_string, self.cwd).run(stream_output=stream_output)
            success = self._executor.success
            if not success and not stream_output and self._executor.stderr:
                print(self._executor.stderr.strip())

        if verbose: print(f"--- [结束 (成功: {success})] ---")
        return success

    def execute_batch(self, commands: List[str], stream_output: bool = False, verbose: bool = True) -> bool:
        """
        按顺序执行一个命令列表。如果任何命令失败，则中断执行。
        
        参数:
        commands (List[str]): 要执行的命令字符串列表。
        stream_output (bool): 是否实时打印子命令的输出。在静默模式下通常为 False。
        verbose (bool): 是否打印每一步的执行信息。设置为 False 以获得最大性能。
        """
        if verbose:
            print(f"\n--- [开始批量执行 {len(commands)} 条命令 (详细模式)] ---")
        
        start_time = time.perf_counter()

        for i, command in enumerate(commands):
            if verbose:
                print(f"\n[步骤 {i+1}/{len(commands)}] > {command}")
            
            # 关闭 execute 自身的 verbose，由本方法统一控制
            success = self.execute(command, stream_output=stream_output, verbose=False)
            
            if not success:
                print(f"\n[!! 批量执行失败] 在步骤 {i+1} 处中断: '{command}'")
                # 如果执行器有错误输出，也一并打印出来
                if self._executor._executed and self._executor.stderr:
                    print("错误详情:", self._executor.stderr.strip())
                print("--- [批量执行已终止] ---")
                return False
        
        end_time = time.perf_counter()
        duration = end_time - start_time

        if verbose:
            print(f"\n--- [批量执行成功] 所有命令均已成功执行 ---")
        else:
            # 在静默模式下，成功后只打印一条最终的摘要
            print(f"--- [批量执行成功] {len(commands)} 条命令在 {duration:.4f} 秒内完成。 ---")
            
        return True
    
def run_interactive(self):
        """启动一个交互式循环，模拟真实终端。"""
        while True:
            try:
                command = input(self.prompt)
                if command.lower() in ["exit", "quit"]:
                    print("终端会话结束。")
                    break
                self.execute(command)
            except KeyboardInterrupt: # Ctrl+C
                print("\n终端会话结束。")
                break

if __name__ == "__main__":
    # 创建一个大型批量任务
    num_ops = 1000
    batch_create = [f"echo 'file {i}' > test_{i}.txt" for i in range(num_ops)]
    batch_delete = [f"del test_{i}.txt" if platform.system() == "Windows" else f"rm test_{i}.txt" for i in range(num_ops)]
    
    large_batch = (
        ["mkdir perf_test_dir", "cd perf_test_dir"] +
        batch_create +
        batch_delete +
        ["cd ..", "rmdir perf_test_dir"]
    )
    total_commands = len(large_batch)
    print(f"准备执行包含 {total_commands} 条命令的大型批量任务...")

    # --- 测试1: 详细模式 (Verbose Mode) ---
    print("\n" + "="*50)
    print(">>> 测试 1: 详细模式 (verbose=True)")
    
    # 清理环境
    if os.path.exists("perf_test_dir"):
        import shutil
        shutil.rmtree("perf_test_dir")

    session_verbose = TerminalSession(start_dir=".")
    start_verbose = time.perf_counter()
    session_verbose.execute_batch(large_batch, stream_output=False, verbose=True)
    end_verbose = time.perf_counter()
    duration_verbose = end_verbose - start_verbose
    print(f"\n[性能报告] 详细模式耗时: {duration_verbose:.4f} 秒")


    # --- 测试2: 静默模式 (Silent Mode) ---
    print("\n" + "="*50)
    print(">>> 测试 2: 静默模式 (verbose=False)")

    # 清理环境
    if os.path.exists("perf_test_dir"):
        import shutil
        shutil.rmtree("perf_test_dir")

    session_silent = TerminalSession(start_dir=".")
    start_silent = time.perf_counter()
    # 注意这里 verbose=False
    session_silent.execute_batch(large_batch, stream_output=False, verbose=False)
    end_silent = time.perf_counter()
    duration_silent = end_silent - start_silent
    # 在静默模式下，execute_batch 已经打印了耗时，这里再打印一次总时间
    print(f"[性能报告] 静默模式总耗时: {duration_silent:.4f} 秒")
    
    # --- 性能对比总结 ---
    print("\n" + "="*50)
    print(">>> 性能对比总结 <<<")
    print(f"详细模式 (带大量打印): {duration_verbose:.4f} 秒")
    print(f"静默模式 (无过程打印): {duration_silent:.4f} 秒")
    if duration_silent > 0:
        speedup = duration_verbose / duration_silent
        print(f"性能提升了约 {speedup:.2f} 倍！")