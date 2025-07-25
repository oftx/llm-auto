# 创建脚本
cat << 'EOF' > temp_commands.sh
#!/bin/bash
cd ..
ls -l
pwd
echo "Done"
EOF

# 赋予执行权限
chmod +x temp_commands.sh

# 使用 source 执行
source temp_commands.sh

# 可选：清理
rm temp_commands.sh