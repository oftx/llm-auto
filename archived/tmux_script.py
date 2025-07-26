import libtmux
import time

server = libtmux.Server()

session_name = "my_persistent_session"
sessions = server.sessions.filter(session_name=session_name)
if sessions:
    session = sessions[0]
else:
    session = None
if not session:
    session = server.new_session(session_name=session_name)

window = session.windows[0]
pane = window.panes[0]

print("可在新终端使用以下命令连接会话: tmux attach -t", session_name)

# 1. 自动化运行命令
pane.send_keys('ls -l', enter=True)
pane.send_keys('echo Finish!', enter=True)
server.cmd('wait-for', '-S', 'Finish!')
output = pane.capture_pane()
print("\n".join(output))

# 3. 继续执行其他命令
pane.send_keys('echo "交互完成，继续执行..."', enter=True)
time.sleep(1)
# print("\n".join(pane.capture_pane()))

# 脚本结束后，tmux 会话依然在后台运行