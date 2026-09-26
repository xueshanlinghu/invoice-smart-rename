# 仓库协作与项目接手说明

本文是新会话接手本项目时的首要上下文。开始工作前应先阅读本文和 `README.md`，再执行 `git status --short`，不得覆盖或丢弃用户已有改动。

## 提交流程（强制）

1. 当用户提出要 `commit` 时，必须先输出本次变更清单（按模块/文件说明）。
2. 同时给出拟提交的 `commit message` 草案，供用户确认。
3. 只有在用户明确确认后，才能执行 `git add` / `git commit`。
4. 未经确认，禁止提交；若误提交，必须第一时间说明并等待用户指令。

## Commit Message 规范

1. 必须使用中文。
2. 必须是详细说明，包含改动范围与目的。
3. 禁止使用简短、纯英文或信息量不足的提交说明。

## 前端验证规则

1. 前端小改动默认不执行 `npm run build:web`。
2. 仅在以下场景执行构建验证：
   - 用户明确要求执行构建；
   - 改动范围较大或涉及核心流程（如路由、状态管理、构建配置、打包配置）；
   - 需要在提交前做一次完整收敛验证。
3. 若未执行构建，需要在回复中明确说明“本次未执行 build”。

## 项目目标

这是一个 Windows 优先的桌面发票处理工具，用于：

1. 拖入 PDF、PNG、JPG/JPEG 发票；
2. 调用硅基流动视觉模型提取开票日期、项目名称和价税合计；
3. 根据关键词映射生成发票类别；
4. 按模板生成新文件名并支持人工核对、编辑、预览；
5. 对选中记录批量改名，直接修改原文件所在位置。

项目强调避免不必要的云端重复识别，以降低模型调用费用。

## 技术架构

- 前端：Vue 3、TypeScript、Pinia、Naive UI、Vite。
- 后端：Python 3.12+、FastAPI、Pydantic、httpx、pypdfium2，使用 uv 管理。
- 桌面端：Tauri 2、Rust。
- 数据：SQLite，保存任务快照、设置和成功的 OCR 缓存。
- Windows 成品：PyInstaller 将 FastAPI 打成 sidecar，再由 Tauri/NSIS 打包。

主要目录：

- `frontend/src/App.vue`：主界面、设置页、识别操作、筛选和备份入口。
- `frontend/src/stores/invoice.ts`：任务状态、识别/改名流程及本地编辑。
- `frontend/src/api/`：FastAPI 与 Tauri 命令调用封装。
- `backend/app/main.py`：HTTP API、导入、缓存、重算、改名和备份接口。
- `backend/app/storage.py`：SQLite 任务、缓存、设置存储。
- `backend/app/services/ocr/`：硅基流动调用和字段标准化。
- `backend/app/services/settings_store.py`：设置读取、持久化和分类推断。
- `src-tauri/src/lib.rs`：文件预览/改名命令及 sidecar 生命周期。
- `scripts/build-backend-win.ps1`：Windows sidecar 构建脚本。

## 当前核心行为与设计约束

### 识别与费用控制

- 主操作“识别未处理项”只处理 `pending` 记录，不应自动重新识别成功记录。
- “重试失败项”只处理 `failed` 记录。
- “重新识别选中”会设置 `force_refresh=true`、绕过缓存，并必须保留费用风险确认。
- “停止识别”只停止尚未发出的后续请求；当前已发送的单条请求会正常结束。
- 每条记录保存 `recognition_source`、`recognized_at`、`recognition_model`、`prompt_version` 和 `cloud_call_count`。
- 成功识别结果才写入 OCR 缓存；云端失败不会覆盖已有成功缓存。

### OCR 缓存

- 缓存键由“文件 SHA-256 + 服务商 + 模型 + 提示词版本”组成。
- 关键词映射和文件名模板不能进入 OCR 缓存键。
- 相同文件、模型和提示词版本再次导入时应直接恢复缓存，不调用云端。
- 强制重新识别是显式绕过缓存的唯一常规入口。

### 零费用重算

- 修改模型或 API Key：只影响后续云端识别。
- 修改关键词映射：使用已有 `item_name + old_name` 重新分类，不调用云模型。
- 修改命名模板：仅重新计算文件名，不调用云模型。
- 后端接口为 `POST /api/tasks/{task_id}/recalculate`，操作值为 `category` 和/或 `name`。
- 设置保存后，界面应明确提示本次重算未调用云模型。

### 导入、持久化与备份

- 再次拖入文件默认追加到当前任务，按规范化路径和 SHA-256 去重。
- “新建任务”用于从空任务开始。
- 程序启动后自动恢复最近一个非空任务。
- 支持 JSON 任务备份导出/导入；备份不包含实际发票文件和 API Key。
- 单文件上限为 25MB；PDF 上限为 20 页。超限或无效文件不得上传云端。
- 本地人工编辑日期、金额或类别后，来源标记为 `manual`。

### 数据与安全

- 开发模式默认数据目录：Windows 的 `%LOCALAPPDATA%\InvoiceSmartRename`。
- 便携版始终将 SQLite 数据库放在主程序 EXE 所在目录；Tauri 将该目录传给 sidecar，不可写时应明确报错，不得静默改用其他目录。
- 首次运行新版便携程序且同目录无数据库时，从旧 Tauri 应用数据目录通过 SQLite 备份接口迁移，保留旧库，不覆盖已有便携库。
- `.env` 仅作为源码开发的可选初始配置和回退来源，不提交到 Git；便携版不需要它。
- API Key 已从前端 `localStorage` 移到后端 SQLite 数据库；便携版数据库与 EXE 同目录，当前尚未接入 Windows Credential Manager。
- 便携版后端使用动态回环端口和随机会话令牌；除 `/api/health` 外的 API 必须校验 `X-App-Token`。
- 不得在日志、测试输出、回复或提交中泄露真实 API Key。

## 开发与验证命令

首次安装：

```powershell
uv sync --project backend
npm install
```

开发模式需要两个终端：

```powershell
npm run dev:api
npm run tauri:dev
```

常用验证：

```powershell
uv run --project backend pytest -q
npm run test:web
npm run build:web
cd src-tauri
cargo check
cargo check --release
```

当前测试基线：后端 6 项测试、前端 3 项测试。

前端生产构建当前有约 933KB chunk 的 Vite 警告，但构建成功；这属于后续可优化项，不是当前构建失败。

当前环境的 Rust 工具链未安装 `rustfmt`，因此 `cargo fmt --check` 会提示安装 `rustfmt` 组件。未经用户要求，不要为了格式检查擅自修改全局工具链。

## Windows 构建与产物

构建 sidecar：

```powershell
npm run build:backend:win
```

生成完整 NSIS 安装程序：

```powershell
npm run dist:win
```

相关脚本含义：

- `build:backend:win`：PyInstaller 生成带 Rust target triple 后缀的 sidecar。
- `tauri:build:raw`：使用 `src-tauri/tauri.bundle.conf.json` 构建 NSIS。
- `dist:win` / `tauri:build`：先构建 sidecar，再构建 Tauri 安装程序。
- 当前日常分发方式为便携版：`build:backend:win` 后执行 `npx tauri build --no-bundle --config src-tauri/tauri.bundle.conf.json`。运行目录须可写，并保留主程序与 sidecar 两个 EXE。

正常安装包目录：

```text
src-tauri/target/release/bundle/nsis/
```

只验证 release 程序而跳过安装器：

```powershell
npx tauri build --no-bundle --config src-tauri/tauri.bundle.conf.json
```

生成的 release 程序位于 `src-tauri/target/release/invoice-smart-rename.exe`，旁边应有 `invoice-backend.exe`。

## 当前构建状态与已知限制

截至 2026-07-14：

- 后端测试通过：`6 passed`。
- 前端测试通过：`3 passed`。
- `npm run build:web` 通过。
- `cargo check` 和 `cargo check --release` 通过。
- PyInstaller sidecar 构建成功，并通过健康检查和令牌访问检查。
- Tauri release 桌面程序能自动启动内置 sidecar，动态端口健康检查通过。
- NSIS 安装程序尚未在当前机器成功落盘：Tauri 下载 GitHub 上的 NSIS 3.11 工具连续发生网络全局超时；Rust release 和 sidecar 本身均已构建成功。网络恢复后重新运行 `npm run dist:win` 即可。
- 当前未配置代码签名，正式对外分发前应增加 Windows 代码签名证书。
- 当前 API Key 存于应用 SQLite 数据库而非系统凭据库，这是后续安全增强项。

## 当前工作区状态提醒

截至 2026-07-14，上述“持久化、缓存、零费用重算、防重复识别、任务备份、sidecar 和 Windows 构建”是一组尚未提交的工作区改动。

新会话接手时必须：

1. 先执行 `git status --short`；
2. 将现有修改视为用户的重要成果，不得执行 `git reset --hard`、`git checkout --` 或其他丢弃操作；
3. 修改前先确认相关文件的当前内容，不要依据旧提交重写；
4. 只有用户明确要求并确认提交清单与中文 commit message 后，才能提交。

## 后续优化建议

按优先级可继续处理：

1. 网络恢复后完成 NSIS 安装包落盘，并在干净 Windows 10/11 环境安装验收。
2. 接入 Windows Credential Manager 或其他系统凭据库保护 API Key。
3. 对前端大 chunk 做按需导入和拆包优化。
4. 增加任务列表/历史任务管理，而不仅恢复最近任务。
5. 增加缓存管理界面、调用统计和可控的缓存清理。
6. 配置代码签名、版本升级策略和自动发布流水线。
