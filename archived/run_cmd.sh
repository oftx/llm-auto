#!/bin/bash

# 设置脚本在命令失败时退出
set -e

# 定义命令数组
commands=(
    "pwd"
    "cd .."
    "pwd"
)

# 循环运行命令
for cmd in "${commands[@]}"; do
    echo "Running command: $cmd"
    # 执行命令并捕获输出
    if $cmd; then
        echo "Command '$cmd' executed successfully"
    else
        echo "Error: Command '$cmd' failed with exit code $?"
        exit 1
    fi
    echo "-----------------------------"
done

echo "All commands completed successfully"