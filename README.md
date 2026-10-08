# 语言学论辩 Wiki MVP（Linux 版）

## 项目简介

语言学论辩 Wiki MVP 是一个面向语言学论辩与知识沉淀的 Wiki 原型系统，Linux 版，支持通过 Docker 一键启动，方便本地开发、演示与部署。

## 技术栈

- Linux + Docker + Docker Compose v2
- Bash 运维脚本（doctor / start / stop）
- Web 服务统一经 8080 端口对外提供访问
- REST API 健康检查：`/api/v1/ops/live`
- `.env` + `.env.example` 环境变量配置

## 快速开始

1. 复制环境变量并修改密码：

   ```bash
   cp .env.example .env
   # 编辑 .env，修改默认密码
   ```

2. 环境预检：

   ```bash
   ./scripts/doctor.sh
   ```

3. 一键启动：

   ```bash
   ./scripts/start.sh
   ```

4. 访问：

   ```
   http://127.0.0.1:8080
   ```

5. 停止服务（默认保留数据卷）：

   ```bash
   ./scripts/stop.sh
   ```

## 服务说明

- 统一入口：`http://127.0.0.1:8080`
- 健康检查：`http://127.0.0.1:8080/api/v1/ops/live`
- `start.sh` 会执行 `docker compose up --build -d` 并等待 API 就绪。
- `stop.sh` 默认执行 `docker compose down`，保留数据卷。
- `doctor.sh` 检查 docker、compose 版本、8080 端口占用与 `.env`。

## 当前状态

骨架阶段：仅提供基础启动骨架与环境检查，后续功能持续迭代中。
