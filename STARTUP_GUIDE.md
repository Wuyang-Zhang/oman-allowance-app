# 启动指南 (STARTUP_GUIDE)

## 1. 项目概述
本系统用于**自动计算在中国就读的阿曼学生补助**，并输出可结算的人民币（CNY）文件。系统包含：
- 月度生活补助
- 年度学习补助（仅 10 月）
- 毕业后一次性超额行李补助

---

## 2. Windows 离线桌面版（推荐）
### 2.1 环境要求
- Windows 10/11
- Python 3.10+
- 无需浏览器/服务器/网络

### 2.2 构建可执行文件（开发人员操作）
在项目根目录运行：

```bat
build_windows.bat
```

输出目录：
- `dist\OmanAllowanceApp\OmanAllowanceApp.exe`

### 2.3 运行
双击 `OmanAllowanceApp.exe` 即可启动。

### 2.4 数据目录
- 数据库：`%APPDATA%\OmanAllowanceApp\data\oma.db`
- 备份目录：`%APPDATA%\OmanAllowanceApp\backups\`

---

## 3. Web 版（可选，仅用于开发调试）
### 3.1 环境要求
- Linux
- Python 3.9+

### 3.2 安装（本机前缀）
```bash
python3 -m pip install -e ".[web]" --prefix /home/zhangwuyang/CODE/oMA/.local
```

### 3.3 启动命令（本项目实际使用）
```bash
PYTHONPATH=/home/zhangwuyang/CODE/oMA/src:/home/zhangwuyang/CODE/oMA/.local/local/lib/python3.10/dist-packages \
python3 -m oma.web
```

### 3.4 验证运行
- `http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/health`

### 3.5 停止服务
- 终端中按 `Ctrl + C`

---

## 4. 常见启动问题与处理
### 4.1 端口被占用（Web 版）
- 关闭占用端口的旧进程
- 或更换端口

### 4.2 无法访问（Web 版）
- 确认服务已启动
- 确认地址为 `http://127.0.0.1:8000`

---

# STARTUP GUIDE (English)

## 1. Project Overview
This system **automatically calculates allowances for Omani students studying in China** and produces settlement files in CNY. It covers:
- Monthly living allowance
- Annual study allowance (October only)
- One-time excess baggage allowance after graduation

---

## 2. Windows Offline Desktop App (Recommended)
### 2.1 Requirements
- Windows 10/11
- Python 3.10+
- No browser/server/network required

### 2.2 Build the Executable (Developer)
Run in the project root:

```bat
build_windows.bat
```

Output folder:
- `dist\OmanAllowanceApp\OmanAllowanceApp.exe`

### 2.3 Run
Double-click `OmanAllowanceApp.exe`.

### 2.4 Data Locations
- Database: `%APPDATA%\OmanAllowanceApp\data\oma.db`
- Backups: `%APPDATA%\OmanAllowanceApp\backups\`

---

## 3. Web Version (Optional, Dev Only)
### 3.1 Requirements
- Linux
- Python 3.9+

### 3.2 Install (Local Prefix)
```bash
python3 -m pip install -e ".[web]" --prefix /home/zhangwuyang/CODE/oMA/.local
```

### 3.3 Start Command (Used in This Project)
```bash
PYTHONPATH=/home/zhangwuyang/CODE/oMA/src:/home/zhangwuyang/CODE/oMA/.local/local/lib/python3.10/dist-packages \
python3 -m oma.web
```

### 3.4 Verify
- `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`

### 3.5 Stop
- Press `Ctrl + C` in the terminal

---

## 4. Common Startup Problems
### 4.1 Port In Use (Web)
- Stop the old process
- Or use another port

### 4.2 Connection Refused (Web)
- Ensure the service is running
- Ensure the URL is `http://127.0.0.1:8000`
