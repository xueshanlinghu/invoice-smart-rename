# 发票智能识别并重命名

用于批量导入发票，识别关键信息并完成批量改名。

## 使用前准备

首次使用请准备硅基流动 API Key，并确保网络可访问其接口。

## 使用步骤

1. 进入“设置”页面：
   - 选择模型（默认即可）
   - 填写 API Key（或者在启动前在.env文件中配置）
   - 点击“保存配置”

2. 回到“发票处理”页面：
   - 直接拖拽发票文件到导入区域（支持 `PDF / PNG / JPG / JPEG`）

3. 勾选需要处理的记录，点击“识别选中发票”。

4. 在识别列表中人工核对并修正：
   - 开票日期
   - 类别
   - 金额
   - 新文件名预览会自动更新

5. 点击“执行改名”并确认，完成批量改名。
   - 状态列可查看每条结果（已改名 / 改名失败 / 已跳过）
   - 底部状态栏可查看处理进度和汇总信息

## 启动命令

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

2. 初始化配置文件（首次）：

```bash
copy .env.example .env
```

至少配置：
- `SILICONFLOW_API_KEY`

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

## 许可证

MIT（见 `LICENSE`）
