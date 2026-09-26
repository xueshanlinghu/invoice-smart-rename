# 发票智能识别并重命名

用于批量导入发票，识别关键信息并完成批量改名。

## 使用前准备

首次使用请准备硅基流动 API Key，并确保网络可访问其接口。

## 使用步骤

1. 进入“设置”页面：
   - 选择模型（默认即可）
   - 填写 API Key；便携版不需要 `.env`
   - 点击“保存配置”

2. 回到“发票处理”页面：
   - 直接拖拽发票文件到导入区域（支持 `PDF / PNG / JPG / JPEG`）

3. 点击“识别未处理项”。

   - “识别未处理项”只调用尚未识别的记录。
   - “重试失败项”只处理失败记录。
   - “重新识别选中”会绕过缓存并产生新的模型调用，执行前会再次确认。

4. 在识别列表中人工核对并修正：
   - 开票日期
   - 类别
   - 金额
   - 新文件名预览会自动更新

5. 点击“执行改名”并确认，完成批量改名。
   - 状态列可查看每条结果（已改名 / 改名失败 / 已跳过）
   - 底部状态栏可查看处理进度和汇总信息

## 识别缓存与本地数据

- 任务、设置和成功的识别结果保存在本机 SQLite 数据库中，重启程序后会恢复最近任务。
- 同一文件在相同模型和提示词版本下会优先复用缓存；修改关键词映射或命名模板不会再次调用云模型。
- 再次拖入文件会追加到当前任务，并按路径和文件内容去重；点击“新建任务”可从空列表开始。
- 支持导出和导入 JSON 任务备份。备份包含识别字段和原文件路径，不包含发票文件本身。
- Windows 便携版将 `invoice-smart-rename.sqlite3` 放在 `invoice-smart-rename.exe` 所在目录，API Key、分类映射、任务和 OCR 缓存都在其中；该目录必须可写。
- 首次启动新版便携程序时，若程序目录还没有数据库，会从旧的 `%APPDATA%\com.myfox.invoice-smart-rename` 创建一份完整 SQLite 快照；旧数据库保留，已有同目录数据库不会被覆盖。
- 源码开发模式仍使用 `%LOCALAPPDATA%\InvoiceSmartRename`，可通过 `INVOICE_APP_DATA_DIR` 指定其他位置。关闭程序后搬运便携版时，应一起复制两个 EXE、数据库及存在的 `-wal` / `-shm` 文件。
- 单文件最大 25MB，PDF 最大 20 页；超出限制的文件不会上传到云端。
- 人工修改日期、类别、金额后会自动保存；状态栏显示“人工修改待保存”时，请等待保存完成再关闭程序。导出备份前也会先完成保存。

## 源码开发

如果你是本地源码运行，请使用以下命令：

1. 安装运行环境（Windows）：

安装 Node.js（含 npm）：

官网：https://nodejs.org/

```powershell
winget install -e --id OpenJS.NodeJS.LTS
```

安装 `uv`（二选一）：

官网：https://docs.astral.sh/uv/

```powershell
winget install -e --id astral-sh.uv
```

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装 `Rust + cargo`：

```powershell
winget install -e --id Rustlang.Rustup
rustup default stable-msvc
```

安装 Windows C++ 构建工具（MSVC）：

官网：https://visualstudio.microsoft.com/visual-cpp-build-tools/

也可直接下载 Build Tools 安装器：
https://aka.ms/vs/17/release/vs_BuildTools.exe

使用官网安装器时，建议勾选：
- 工作负载：`使用 C++ 的桌面开发`
- 组件：`MSVC v143 - VS 2022 C++ x64/x86 生成工具`
- 组件：`Windows 10/11 SDK`
- 组件：`用于 Windows 的 C++ CMake 工具`

```powershell
winget install -e --id Microsoft.VisualStudio.2022.BuildTools
```

安装 WebView2 Runtime：

说明：Windows 11 大多数情况下已预装（随 Edge 提供），但建议仍执行安装或先检查版本。

```powershell
winget install -e --id Microsoft.EdgeWebView2Runtime
```

安装后建议重开终端，并检查：

```powershell
node -v
npm -v
uv --version
rustc --version
cargo --version
```

检查 WebView2 Runtime 是否已安装及版本（保存为 .ps1 脚本并双击执行）：

```powershell
$webviewGuid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
$paths = @(
  "HKLM:\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\$webviewGuid",
  "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\$webviewGuid",
  "HKCU:\\Software\\Microsoft\\EdgeUpdate\\Clients\\$webviewGuid"
)
$found = $false
foreach ($p in $paths) {
  if (Test-Path $p) {
    $ver = (Get-ItemProperty -Path $p -ErrorAction SilentlyContinue).pv
    if ($ver) {
      Write-Host "WebView2 Runtime version: $ver"
      $found = $true
      break
    }
  }
}
if (-not $found) {
  Write-Host "WebView2 Runtime 未检测到，请先安装 Microsoft Edge WebView2 Runtime。"
}
```

2. 初始化配置文件（可选）：

```bash
copy .env.example .env
```

也可以不创建 `.env`，启动后直接在设置页保存 API Key；`.env` 仅作为源码开发时的可选初始配置和回退来源。便携版不需要携带它。

3. 安装依赖：

```bash
uv sync --project backend
npm install
```

4. 启动后端 API：

```bash
npm run dev:api
```

5. 启动桌面程序：

```bash
npm run tauri:dev
```

开发模式仍需分别保持后端 API 和 Tauri 两个终端运行，以便后端热重载。

## 构建 Windows 便携版

Windows 便携版由 Tauri 2 程序和 PyInstaller 打包的 FastAPI sidecar 组成。最终用户不需要安装 Python、Node.js、Rust 或 uv。

### 构建环境

在 Windows x64 上安装：

- Node.js LTS、uv、Rust stable-msvc；
- Visual Studio 2022 Build Tools 的“使用 C++ 的桌面开发”、MSVC 和 Windows SDK；
- WebView2 Runtime（Windows 10/11 通常已经安装）。

首次构建先安装依赖：

```powershell
uv sync --project backend --extra build
npm install
```

生成日常使用的便携版：

```powershell
npm run build:backend:win
npx tauri build --no-bundle --config src-tauri/tauri.bundle.conf.json
```

双击 `src-tauri/target/release/invoice-smart-rename.exe`；同目录须保留 `invoice-backend.exe`。数据库也会放在该目录，程序会自动启动后端。将这两个 EXE 与数据库放在同一可写文件夹，即可在另一台 Windows 电脑使用。

### 可选：NSIS 安装程序

生成完整 NSIS 安装程序：

```powershell
npm run dist:win
```

该命令依次执行：

1. `npm run build:backend:win`：生成 `src-tauri/binaries/invoice-backend-x86_64-pc-windows-msvc.exe`；
2. 前端类型检查和静态构建；
3. Tauri release 构建并把后端 sidecar 一并打包。

安装程序输出目录：

```text
src-tauri/target/release/bundle/nsis/
```

当前数据目录设计面向便携版。NSIS 若安装在 `Program Files` 等不可写目录，程序无法在 EXE 旁保存数据库；日常分发请使用上面的便携版。

多屏幕试用时，可在不同缩放比例的屏幕间来回拖动窗口，再试最小化和恢复。程序会在窗口标题栏移出所有屏幕可用区域后自动移回；若仍找不到窗口，可点击 Windows 系统托盘中的程序图标，选择“恢复窗口到主屏”。托盘菜单中的“退出程序”可直接关闭程序。

也可继续使用兼容命令：

```powershell
npm run tauri:build
```

它等价于 `npm run dist:win`。当前仅生成 NSIS `*-setup.exe`，不生成 MSI，以减少额外的 WiX/VBSCRIPT 环境依赖。

### 发布前验收

建议在未安装开发工具的干净 Windows 10/11 环境中验证：

1. 安装并启动程序，确认不需要单独运行后端；
2. 保存 API Key，导入并识别一张发票；
3. 重启程序，确认任务自动恢复；
4. 修改关键词映射，确认界面提示“未调用云模型”；
5. 完成预览、人工修正和文件改名；
6. 验证导出/导入任务备份。

未进行代码签名时，Windows 可能显示未知发布者或 SmartScreen 提示；对外分发前建议配置正式代码签名证书。

## 验证命令

```powershell
uv run --project backend pytest -q
npm run test:web
npm run build:web
cd src-tauri
cargo check
cargo check --release
```

## 许可证

MIT（见 `LICENSE`）
