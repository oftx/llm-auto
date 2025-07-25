#!/bin/bash

# --- 配置 ---
NUM_FILES=1000
TEST_DIR="bash_perf_test"

# --- 清理环境 ---
if [ -d "$TEST_DIR" ]; then
  echo "清理旧的测试目录: $TEST_DIR"
  rm -rf "$TEST_DIR"
fi
mkdir "$TEST_DIR"
cd "$TEST_DIR"

echo "=========================================================="
echo "测试开始: 在单个 Bash 进程中创建和删除 $NUM_FILES 个文件"
echo "=========================================================="

# 使用 time 命令来精确测量整个代码块的执行时间
time {
  # --- 1. 创建文件 ---
  echo "正在创建 $NUM_FILES 个文件..."
  for i in $(seq 1 $NUM_FILES); do
    # 直接在 shell 中执行，没有新进程开销
    echo "file $i" > "test_$i.txt"
  done

  # --- 2. 删除文件 (使用循环，与 Python 逻辑最接近) ---
  echo "正在使用循环删除 $NUM_FILES 个文件..."
  for i in $(seq 1 $NUM_FILES); do
    rm "test_$i.txt"
  done
}

echo "=========================================================="
echo "          现在展示 Shell 的原生性能优化"
echo "=========================================================="
# 这个版本展示了 shell globbing 的威力，比循环快得多
time {
    echo "正在创建 $NUM_FILES 个文件..."
    for i in $(seq 1 $NUM_FILES); do
        echo "file $i" > "test_$i.txt"
    done
    
    echo "正在使用单个 'rm' 命令和通配符删除所有文件..."
    # 这一步比循环快得多
    rm test_*.txt
}

# --- 最终清理 ---
cd ..
rm -rf "$TEST_DIR"
echo "测试完成，环境已清理。"