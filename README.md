# U8Assistant

用于学校“业财税一体化”实验的 Windows 桌面辅助工具。第一阶段只完成 PDF 任务阅读、惰性页面渲染、Mock 自动化边界和机房诊断；它**不会**猜测用友 U8 控件、点击固定坐标、自动保存、记账、审核或结账。

## 当前能力

- 使用 PyMuPDF 的 `doc.get_toc()` 读取原生 PDF bookmarks，不对整份 PDF OCR。
- 输出 `data/tasks.json`，保留原始标题、子任务、页码和所有解析警告。
- 将 `任务【32】——任务【35】` 一类书签标为 `kind: "range"`，不会伪装为普通单任务。
- 点击任务时才渲染所需的 PDF PNG，缓存到 `screenshots/pdf_cache/`。
- Tkinter 界面含任务浏览、前后翻页、缩放、Mock Automation Panel 与紧急停止热键 `Ctrl + Alt + Q`。
- 默认 `MockU8Controller` 只写入形如 `[DRY RUN] set_text field=date value=12月7日` 的日志。`save()` 明确拒绝自动保存。
- `src/u8/probe.py` 在 Windows 机房收集窗口与控件证据，自动产出摘要、候选交互控件和窗口层级；任一 pywinauto backend、控件或截图出错也会继续生成其余诊断文件。
- `U8诊断工具.exe`（由 Windows 构建产生）提供只有“开始诊断”一个主要按钮的中文界面；不会要求普通使用者打开命令行、安装 Python 或查找日志文件。

## 安装与启动

目标运行环境为 **Windows + Python 3.11+**。创建虚拟环境后安装依赖：

```powershell
cd u8-assistant
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

将 `业财税2023.pdf` 放到项目根目录，或复制 `config/config.example.json` 为 `config/config.json` 并设置 `pdf_path`。也可以在当前用户 Downloads 目录中保留同名 PDF。然后运行：

```powershell
python main.py
```

无界面验证和重新生成任务 JSON：

```powershell
python main.py --pdf "C:\实验资料\业财税2023.pdf" --no-gui
python -m unittest discover -s tests -v
```

## `tasks.json` 页码规则

PDF outline 页码是 **从 1 开始** 的；PyMuPDF 的 `load_page()` 是 **从 0 开始** 的。解析结果使用人类可读的 1-based 页码，渲染时仅在 `page_number - 1` 处转换一次。

一个一级任务的正常页面范围是“当前一级 bookmark 页”到“下一个一级 bookmark 页 - 1”。若书签页码无效、缺失、倒序或没有可靠的后续页，工具会缩小到安全页面（或无页面），并在 `warnings` 中注明，而不是猜测范围。

## 去机房前后的 U8 Probe 流程

### 普通使用者：只用诊断工具 EXE

双击 `U8诊断工具.exe`，然后：

1. 打开“U8 企业应用平台”。
2. 进入需要测试的页面。
3. 点击“开始诊断”。

工具只读取窗口和控件信息，绝不会点击、输入、保存或修改 U8。成功后会在桌面自动生成 `U8诊断结果_YYYYMMDD_HHMMSS.zip`，界面提供“打开文件位置”。如果没找到 U8，界面会提示先确认 U8 窗口保持打开；若可能是权限不一致，则提示关闭工具后右键“以管理员身份运行”。不会向普通使用者显示 traceback、Python、backend 或 JSON 术语。

### 开发者：Windows 上构建一次 EXE

本开发机是 macOS，不能直接生成可用的 Windows EXE。将项目放到 Windows 且已安装 Python 3.11+ 的开发机后，唯一需要执行的步骤是：

```powershell
build_windows.bat
```

脚本会安装构建依赖并生成 `dist/U8诊断工具.exe`。之后把这个 EXE 交给普通使用者即可；他们的电脑不需要 Python、pip 或命令行。

`U8诊断工具.spec` 配置了 PyInstaller one-file/windowed 构建，并纳入 pywinauto、comtypes、Pillow 与 pywin32 所需的 hidden imports。请在目标 Windows 版本上实际启动一次 EXE 后再分发。

### 开发者：由 GitHub Actions 自动构建（推荐）

macOS 不可交叉编译 Windows EXE，因此项目已包含 `.github/workflows/build-windows-exe.yml`。将项目提交到 GitHub 后：

1. 推送任意分支，或在 GitHub 的 **Actions** 页面手动运行 **Build U8 Diagnostics Windows EXE**。
2. GitHub 的 Windows 虚拟机会安装 Python 3.11 依赖、运行单元测试，并执行 PyInstaller。
3. 在该运行记录底部的 **Artifacts** 下载 `U8诊断工具-windows`。
4. 解压下载内容，得到 `U8诊断工具.exe`；将它复制到机房电脑后即可双击运行。

这个 workflow 使用 GitHub 托管的 Windows 环境，不会在 macOS 上假装生成可用的 EXE。它与本地 `build_windows.bat` 产出相同的 `dist/U8诊断工具.exe`。

### 技术人员：命令行 Probe（保留）

在已登录 U8、且希望诊断的目标页面真实可见时，执行：

```powershell
cd u8-assistant
python -m src.u8.probe
```

连续诊断不同功能页时，用标签区分目录：

```powershell
python -m src.u8.probe --label u8_main
python -m src.u8.probe --label purchase_order
python -m src.u8.probe --label supplier_popup --backend uia
```

默认同时采集 `win32` 和 `uia`。可用 `--backend win32`、`--backend uia` 或 `--backend both` 选择；如机房政策不允许截图，追加 `--no-screenshot`。标签会安全地转为目录名，例如 `diagnostics/20260923_160000_purchase_order/`。

检查新目录 `diagnostics/YYYYMMDD_HHMMSS/`：

- `environment.json`：Python、Windows、分辨率、DPI scaling。
- `windows.json`：顶层窗口总数、疑似 U8 数量，以及每个窗口的 title、handle、class name、rectangle、visible、enabled。
- `u8_win32.txt`、`u8_uia.txt`：每种 backend 的 `print_control_identifiers()` 输出，即使失败也会记录错误。
- `u8_win32.json`、`u8_uia.json`：控件的 `control_type`、title、automation_id、class_name、rectangle。
- `diagnostics_summary.md`：环境、管理员状态、pywinauto 版本、顶层窗口、两种 backend 的控件总数与按 control type/class name 的统计，以及 automation ID 重复统计。
- `interactive_controls.json`：Edit、Button、ComboBox、TreeView、DataGrid、MenuItem 等候选可交互控件，含 backend、可见/可用状态和矩形。
- `window_hierarchy.json`：每个匹配 U8 窗口到子控件的 `parent`、`child`、`depth` 关系。
- `u8.png` 与 `u8_main.png`：匹配到的主 U8 窗口截图；检测到子窗口/对话框时还会生成 `u8_dialog_01.png` 等。未匹配或关闭截图时会有 `screenshot_error.txt`。
- `diagnostics_errors.log`：任何 backend、窗口、控件访问或截图异常的上下文记录。

带回这些诊断文件后，才可以为已证实的窗口和控件条件构建 adapter。不要把密码、公司账套资料或敏感业务数据加入诊断包。

## 安全边界

`PyWinAutoU8Controller` 是未来的通用桥接层，当前没有 U8 专用 selector。业务层只能传递语义化 `ControlTarget`，不能使用屏幕坐标。真实实现必须沿用：Dry Run 默认开启、禁止默认 Save、每步后暂停、任何异常立即停止并记日志，以及用户人工确认才能继续。

本项目不访问 U8 数据库或 SQL Server，不保存账号密码，也不自动填写真实凭证、记账、审核、结账。

## 项目结构（诊断相关）

```text
u8-assistant/
├── diagnostic_main.py          # U8诊断工具.exe 的 GUI 入口
├── build_windows.bat           # Windows 开发者唯一构建步骤
├── U8诊断工具.spec              # PyInstaller one-file/windowed 配置
├── src/
│   ├── gui/diagnostic_window.py
│   └── u8/
│       ├── probe.py             # 只读采集
│       └── diagnostic_bundle.py # 桌面 ZIP 打包
└── tests/test_diagnostic_bundle.py
```

未来的 `U8Assistant.exe` 也应采用相同原则：终端用户双击程序、在 GUI 中选择任务和确认步骤；Python、pip、日志路径及自动化实现细节均由程序隐藏。本阶段仍未实现任何真实填写功能。
