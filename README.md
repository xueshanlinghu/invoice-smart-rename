# 发票智能识别并重命名

基于 Tauri + Vue + FastAPI 的桌面工具：导入发票文件，调用云端视觉大模型提取字段，人工复核后批量改名。

## 功能

- 支持导入 `PDF / PNG / JPG / JPEG`
- 支持拖拽导入（桌面窗口内直接拖入）
- 云端结构化识别字段：
  - `invoice_date`（开票日期）
  - `item_name`（项目名称）
  - `amount`（价税合计小写金额）
- 关键词映射自动分类（未命中自动归为“其他”）
- 命名模板支持 `{date}`、`{category}`、`{amount}`
- 手工修改后批量执行改名
- 设置项写入根目录 `.env` 并立即生效

## 环境准备

- Node.js 20+
- Rust（含 `cargo`）
- Tauri CLI（通过项目依赖安装）
- Python 3.12+
- uv

## 配置

1. 复制配置模板：

```bash
copy .env.example .env
```

2. 至少配置以下项：

- `SILICONFLOW_API_KEY`
- `SILICONFLOW_MODEL`（默认 `Qwen/Qwen3-VL-32B-Instruct`）
- `APP_HOST`、`APP_PORT`（后端监听地址）
- `VITE_DEV_SERVER_HOST`、`VITE_DEV_SERVER_PORT`（前端开发端口）

说明：
- 前端 API 地址默认自动拼接为 `http://APP_HOST:APP_PORT`
- 如需手工覆盖，可设置 `VITE_API_BASE_URL`

## 安装依赖

```bash
uv sync --project backend
npm install
```

## 开发启动

1. 启动后端 API：

```bash
npm run dev:api
```

2. 启动桌面开发（包含前端热更新）：

```bash
npm run tauri:dev
```

可选：仅调试前端页面时使用：

```bash
npm run dev:web
```

## 打包

```bash
npm run tauri:build
```

## 目录说明

- `backend/`：FastAPI 服务与识别/命名逻辑
- `frontend/`：Vue 3 界面
- `src-tauri/`：Tauri 桌面壳与本地改名命令

## 许可证

MIT（见 `LICENSE`）
