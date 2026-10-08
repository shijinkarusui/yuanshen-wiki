# 论辩 Wiki · Windows 部署指南

## 一次性准备（只需做一次）

### 1. 安装 Python 3.12+
从 https://www.python.org/downloads/ 下载，安装时勾选 **"Add python.exe to PATH"**

### 2. 安装 PostgreSQL 16
从 https://www.postgresql.org/download/windows/ 下载安装。
记住你设置的 postgres 密码。

安装后创建数据库和用户（在开始菜单找到 "SQL Shell (psql)"）：
```sql
-- 输入 postgres 密码登录后执行：
CREATE USER lingdebate WITH PASSWORD 'lingdebate';
CREATE DATABASE lingdebate OWNER lingdebate;
```

### 3. 复制项目文件
把整个 `lingdebate-wiki` 文件夹复制到你 Windows 电脑上，比如 `D:\lingdebate-wiki`

### 4. 安装 Python 依赖
```cmd
cd D:\lingdebate-wiki
python -m venv .venv
.venv\Scripts\activate
cd backend
pip install -r requirements.txt
```

### 5. 初始化数据库
```cmd
cd D:\lingdebate-wiki\backend
set DATABASE_URL=postgresql+psycopg://lingdebate:lingdebate@localhost:5432/lingdebate
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.db.seed
```

## 日常使用

双击运行 `deploy\windows\启动.bat`，然后：

- **本机访问**：http://localhost:8000
- **手机/其他设备访问**（需连同一 WiFi）：http://你的电脑IP:8000
  - 在 cmd 输入 `ipconfig`，找到"无线局域网适配器"的 IPv4 地址，比如 192.168.1.100
  - 手机浏览器输入 http://192.168.1.100:8000

账号：`demo-owner` / `demo1234`

## 防火墙

如果是第一次，其他设备连不上时：
Windows 设置 → 防火墙 → 允许应用通过防火墙 → 给 Python 放行，
或者直接放行 8000 端口入站。
