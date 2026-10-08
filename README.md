# 语言神wiki · 语言学论辩知识图谱

面向语言学论辩与知识沉淀的 Wiki 系统：结构化记录争议问题、人物、文献、论述原文（段落级锚点），支持关系对读、知识图谱、历史版本与撤销。

## 技术栈

- 后端：Python + FastAPI + SQLAlchemy，PostgreSQL 16（原生运行）
- 前端：React + TypeScript + Vite，「晴空羽梦」主题
- 部署：原生进程（uvicorn / vite），附 Windows 一键部署包

## 服务说明

| 服务 | 地址 | 说明 |
|---|---|---|
| 前端 + API | `http://127.0.0.1:8000` | 后端同时托管前端生产构建与 API |
| 前端开发服 | `http://127.0.0.1:5173` | vite dev server |
| 健康检查 | `http://127.0.0.1:8000/api/v1/ops/live` | |

PostgreSQL 数据持久化在仓库内 `.pgdata/` 目录（VM 重置不丢数据）。

## 快速开始

环境恢复 / 首次启动（一键）：

```bash
sudo bash scripts/recover-native.sh
```

该脚本会启动 PostgreSQL（使用 `.pgdata` 内数据）、后端 `:8000` 与前端 `:5173`，并做连通性自检。

登录：`demo-owner` / `demo1234`（首次需先在库中创建该账号，见 `scripts/` 说明）。

匿名可读：`/issues/:id`、`/browse`、`/search` 无需登录；写入操作需要登录。

## 功能清单

- 分类森林、争议问题（挂靠分类、归档/恢复）
- 人物、文献（bibliography）
- 论述原文：段落级编辑（改写/前插/后插/拆分/删除/合并）、Unicode 字素簇校验、锚点映射、预览/提交（SHA-256 指纹、冲突保留草稿、幂等键）
- 关系与批注、关系人工校验、校验维度
- 知识图谱查询与可视化（200 节点/500 边上限，点击定位原文）
- 历史版本查询、撤销协调器（段落快照恢复、锚点逆映射）
- 全局检索（LIKE 实现，pg_trgm 不可用环境下的降级方案）
- 自定义字段、issue↔category 挂靠
- 移动端响应式

## 测试

```bash
cd backend && python -m pytest tests/ -q   # 24 个单元测试（段落模拟器、锚点映射）
```

另有 13 项 API 端到端测试（覆盖登录→录入→段落编辑→图谱→历史→撤销全链路）。

## 运维脚本

- `scripts/recover-native.sh` — 一键恢复全部服务（VM 重置后用这个）
- `scripts/backup.sh` / `scripts/restore.sh` — `pg_dump` / `pg_restore` 逻辑备份与恢复
- `scripts/doctor.sh` / `start.sh` / `stop.sh` — 环境检查与启停（Docker 路径已废弃，沙箱不支持）
- `backups/` — 数据库逻辑备份

## Windows 部署

`deploy/windows/` 内含一键部署包与 `启动.bat`，在用户本地 Windows PC 上运行可实现多设备访问（VM 沙箱网络为单向，外部设备无法直连 VM）。

## 已知未完成

- GB/T 7714-2015 文献格式化输出（M03B）
- M09C 验收门禁：契约差异检查、e2e 测试套件
- 全文检索为 LIKE 降级实现（pg_trgm 不可用）
