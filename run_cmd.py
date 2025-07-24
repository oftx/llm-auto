import subprocess
import platform
import threading
import os
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

    # ... _stream_reader, _run_streaming, _run_blocking 等方法保持不变 ...
    # 它们现在会使用 self.command_string 和 self.cwd
    
    # run 方法稍微调整，以确保 reset() 已被调用
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

    # ... (所有属性和内部方法保持不变) ...
    def _stream_reader(self, stream, output_lines: List[str], prefix: str, print_stream: bool):
        # 此方法不变
        for line in iter(stream.readline, ''):
            if print_stream:
                print(f"{prefix} {line.strip()}", flush=True)
            output_lines.append(line)
        stream.close()

    def _run_streaming(self):
        # 此方法不变，它会使用 self.command_string 和 self.cwd
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
        # 此方法不变，它会使用 self.command_string 和 self.cwd
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

    # ... prompt 和 _handle_cd 方法不变 ...
    @property
    def prompt(self) -> str:
        # 此方法不变
        display_path = self.cwd
        if platform.system() != "Windows":
            home_dir = os.path.expanduser("~")
            if self.cwd.startswith(home_dir):
                display_path = "~" + self.cwd[len(home_dir):]
        return f"{display_path} $ "
        
    def _handle_cd(self, target_dir: str) -> bool:
        # 此方法不变
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
            # <<< 核心变化：复用 executor 实例
            self._executor.reset(command_string, self.cwd).run(stream_output=stream_output)
            success = self._executor.success
            
            if not success and not stream_output and self._executor.stderr:
                print(self._executor.stderr.strip())

        if verbose: print(f"--- [结束 (成功: {success})] ---")
        return success

    # ... execute_batch 和 run_interactive 方法完全不变，因为它们依赖于 execute() ...
    def execute_batch(self, commands: List[str], stream_output: bool = True) -> bool:
        # 此方法逻辑不变
        print(f"\n--- [开始批量执行 {len(commands)} 条命令] ---")
        for i, command in enumerate(commands):
            print(f"\n[步骤 {i+1}/{len(commands)}] > {command}")
            success = self.execute(command, stream_output=stream_output, verbose=False)
            if not success:
                print(f"\n[!! 批量执行失败] 在步骤 {i+1} 处中断: '{command}'")
                print("--- [批量执行已终止] ---")
                return False
        print("\n--- [批量执行成功] 所有命令均已成功执行 ---")
        return True
    
    def run_interactive(self):
        # 此方法逻辑不变
        pass

# --- 主程序入口，功能和之前一样，但内部实现更高效 ---
if __name__ == "__main__":
    import time

    # 创建一个包含大量命令的列表来测试性能
    # 我们将创建和删除100个小文件
    num_files = 1000
    batch_create = [f"echo 'file {i}' > test_{i}.txt" for i in range(num_files)]
    batch_delete = [f"rm test_{i}.txt" if platform.system() != "Windows" else f"del test_{i}.txt" for i in range(num_files)]
    
    # 完整的批量任务
    large_batch = (
        ["mkdir large_batch_test", "cd large_batch_test"] +
        batch_create +
        batch_delete +
        ["cd ..", "rmdir large_batch_test"]
    )
    
    print(f">>> 准备执行包含 {len(large_batch)} 条命令的大型批量任务...")

    # 清理环境
    if os.path.exists("large_batch_test"):
        import shutil
        shutil.rmtree("large_batch_test")

    session = TerminalSession()
    
    start_time = time.perf_counter()
    # 使用非流式输出以最大化测试对象创建的性能差异
    session.execute_batch(large_batch, stream_output=False)
    end_time = time.perf_counter()
    
    print(f"\n[性能报告] 使用复用 Executor 执行 {len(large_batch)} 条命令耗时: {end_time - start_time:.4f} 秒")
    
    # 你可以尝试对比上一版代码的运行时间，会发现此版本在处理大量命令时速度更快。