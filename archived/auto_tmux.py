import libtmux
import os
import time

class InteractiveTerminal:
    """
    一个使用 libtmux 实现的自动化交互式终端。
    """

    def __init__(self, session_name: str = "interactive_terminal"):
        """
        初始化交互式终端。

        Args:
            session_name (str, optional): tmux 会话的名称. 默认为 "interactive_terminal".
        """
        self.server = libtmux.Server()
        # 如果已存在同名会话，先杀掉，确保每次都是全新的会话
        if self.server.find_where({"session_name": session_name}):
            self.server.kill_session(session_name)
        self.session_name = session_name
        self.session = self.server.new_session(session_name=self.session_name, attach=False)

    def get_active_pane(self):
        """
        获取当前活动的窗格。

        Returns:
            libtmux.Pane: 当前活动的窗格对象。
        """
        return self.session.active_pane

    def run_command_sequence(self, commands: list, capture_file: str):
        """
        在 tmux 窗格中按顺序执行一系列命令，并记录整个过程。
        该方法遵循以下步骤：
        1. 运行 script 命令以开始记录。
        2. 依次执行用户定义的命令。
        3. 运行 exit 以停止 script 并保存日志。

        Args:
            commands (list): 要按顺序执行的命令字符串列表。
            capture_file (str): 用于保存捕获输出的文件名。
        """
        pane = self.get_active_pane()
        if not pane:
            return

        # 步骤 1: 运行 script 命令以开始记录
        pane.send_keys(f"script {capture_file}", enter=True)
        time.sleep(1)  # 给予 script 启动的时间

        # 步骤 2: 依次执行所有提供的命令
        for command in commands:
            pane.send_keys(command, enter=True)
            time.sleep(1.5)  # 模拟输入和等待，方便用户观察

        # 步骤 3: 运行 exit 以停止 script 会话
        pane.send_keys("exit", enter=True)

    def attach_to_session(self):
        """
        附加到 tmux 会话，以便用户可以实时查看和交互。
        """
        # 使用 os.system 来执行 attach，因为它能将控制权完全交给 tmux
        os.system(f"tmux attach-session -t {self.session_name}")

if __name__ == '__main__':
    # 实例化终端对象
    terminal = InteractiveTerminal(session_name="my_auto_session")

    # 定义要按顺序执行的命令列表
    # 例如：检查当前用户，列出主目录内容，然后提示需要 sudo 权限的命令
    command_sequence = [
        "whoami",
        "ls -la ~",
        "echo '现在将尝试运行需要sudo的命令...'",
        "sudo apt-get update" # 这个命令需要用户输入密码
    ]

    # 定义捕获日志的文件名
    output_log_file = "session_log.txt"

    # 执行命令序列
    terminal.run_command_sequence(command_sequence, capture_file=output_log_file)

    print(f"命令正在后台的 tmux 会话 '{terminal.session_name}' 中运行。")
    print(f"完整的会话日志将被保存到 '{output_log_file}'。")
    print("现在将附加到 tmux 会话中以便观察和交互...")
    print("会话结束后，您可以按 Ctrl+b d 手动分离，或等待其自动关闭。")
    time.sleep(2)  # 等待用户阅读信息

    # 附加到会话，让用户看到执行过程
    terminal.attach_to_session()

    print(f"\nTmux 会话已结束。请检查 '{output_log_file}' 文件获取完整的运行记录。")