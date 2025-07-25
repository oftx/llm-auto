import pexpect
child = pexpect.spawn('zsh')
child.sendline('ls -l')
child.expect(pexpect.EOF)
print(child.before.decode())