# U8Assistant

用于学校“业财税一体化”实验的 Windows 桌面辅助工具。第一阶段只完成 PDF 任务阅读、惰性页面渲染、Mock 自动化边界和机房诊断；它**不会**猜测用友 U8 控件、点击固定坐标、自动保存、记账、审核或结账。

学校机房的发布目标是 **Windows 7 32 位（x86）**：只使用 GitHub Actions 产物 `U8Assistant-Win7-x86.exe` 和 `U8诊断工具-Win7-x86.exe`。普通使用者不需要安装 Python、pip 或打开命令行。

## 当前能力

- 使用 PyMuPDF 的 `doc.get_toc()` 读取原生 PDF bookmarks，不对整份 PDF OCR。
- 输出 `data/tasks.json`，保留原始标题、子任务、页码和所有解析警告。
- 将 `任务【32】——任务【35】` 一类书签标为 `kind: "range"`，不会伪装为普通单任务。
- 点击任务时才渲染所需的 PDF PNG，缓存到 `screenshots/pdf_cache/`。
- Tkinter 界面含任务浏览、前后翻页、缩放、Mock Automation Panel 与紧急停止热键 `Ctrl + Alt + Q`。
- 默认 `MockU8Controller` 只写入形如 `[DRY RUN] set_text field=date value=12月7日` 的日志。`save()` 明确拒绝自动保存。
- `src/u8/probe.py` 在 Windows 机房收集窗口与控件证据，自动产出摘要、候选交互控件和窗口层级；任一 pywinauto backend、控件或截图出错也会继续生成其余诊断文件。
- `U8诊断工具.exe`（由 Windows 构建产生）提供只有“开始诊断”一个主要按钮的中文界面；不会要求普通使用者打开命令行、安装 Python 或查找日志文件。
- `U8Assistant.exe`（由 Windows 构建产生）提供人工辅助模式：任务搜索、原始 PDF 查看、保守业务分类、可复制的可靠字段、按业务类型生成的录入清单与自动保存的完成状态；不会自动操作 U8。

## 安装与启动

本地开发环境建议使用 **Python 3.11+**。创建虚拟环境后安装依赖：

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

Windows 桌面上的无关窗口可能拒绝访问或在枚举中瞬间关闭。probe 会逐字段读取窗口信息；AccessDenied、无效 handle、UIA、截图或个别控件失败都只写入 `diagnostics_errors.log`，不会中止已有报告。找到 U8 后，仍会生成 ZIP，并提示“诊断完成，部分系统窗口无法读取，已记录。”

### 开发者：构建 Windows 7 x86 EXE（机房发布版本）

本开发机是 macOS，不能直接生成可用的 Windows EXE。Win7 x86 发布版必须在 Windows 上使用 **32 位 Python 3.8.x** 构建。开发机安装 Python 3.8 x86 后执行：

```powershell
build_win7_x86.bat
```

脚本先打印 Python 版本、`platform.architecture()` 与指针位数；若位数不是 **32** 会直接停止。它只接受锁定依赖的二进制发行包，绝不因安装失败临时编译源码。成功后生成：

- `dist/U8Assistant-Win7-x86.exe`（机房使用）
- `dist/U8诊断工具-Win7-x86.exe`（机房诊断使用）

依赖锁定文件为 `requirements-win7-x86.txt`：Python 3.8 x86 下使用 `PyMuPDF==1.24.11`、`Pillow==10.4.0`、`pywinauto==0.6.9`、`pywin32==306`、`comtypes==1.4.8`、`PyInstaller==5.13.2`。之后把 EXE 交给普通使用者即可；他们的电脑不需要 Python、pip 或命令行。

`U8Assistant-Win7-x86.spec` 和 `U8诊断工具-Win7-x86.spec` 都是 PyInstaller one-file/windowed 构建，不显示控制台黑框；Python runtime 和同一 x86 环境产生的 DLL 会随 EXE 一起打包。`U8诊断工具-Win7-x86.spec` 纳入 pywinauto、comtypes、Pillow 与 pywin32 所需的 hidden imports。

### Win7 PDF 兼容方式

Win7 x86 发布版**不会在运行时导入 PyMuPDF**。CI 先把固定的 `assets/业财税2023.pdf` 预渲染为 `assets/rendered_pages/page_001.jpg` … `page_125.jpg`，并写入页数、150 DPI、尺寸及源 PDF SHA-256 的 `manifest.json`。Win7 spec 只打包这些 JPEG、manifest、`tasks.json` 和 Pillow；缩放也由 Pillow 完成。

因此，即使 Win7 出现 PyMuPDF native DLL 加载失败，任务页面仍可显示。静态页缺失时界面只显示页面不可用提示，不会误报“缺少 PyMuPDF”。Win10/11 x64 版本仍使用原始 PDF/PyMuPDF 的惰性渲染方式。

`build_windows.bat` 仍保留给 Windows 10/11 x64 开发版本，输出名称明确为 `U8Assistant-Win10-x64.exe` 与 `U8诊断工具-Win10-x64.exe`，不要带到学校 Win7 x86 机房。

### 开发者：由 GitHub Actions 自动构建（推荐）

macOS 不可交叉编译 Windows EXE，因此项目已包含 `.github/workflows/build-windows-exe.yml`。将项目提交到 GitHub 后：

1. 推送任意分支，或在 GitHub 的 **Actions** 页面手动运行 **Build U8Assistant Windows executables**。
2. `Package Windows 7 x86 (Python 3.8 x86)` job 明确使用 `actions/setup-python@v5` 的 `python-version: '3.8'` 与 `architecture: 'x86'`，打印运行时信息，并在指针位数不是 `32` 时失败。
3. 该 job 安装 `requirements-win7-x86.txt`、运行单元测试，并以 32 位 PyInstaller 生成 EXE。
4. 在运行记录底部下载 artifact **`U8Assistant-Win7-x86`**，其中包含 `U8Assistant-Win7-x86.exe` 和 `U8诊断工具-Win7-x86.exe`。只把这两个 x86 文件复制到学校电脑。
5. `U8Assistant-Win10-x64` 是额外的 Windows 10/11 x64 artifact，不适用于学校 Win7 32 位电脑。

这个 workflow 只能证明 x86 Python、锁定依赖和 PyInstaller 打包成功；GitHub 运行器不是 Windows 7。**最终仍必须在学校的 Windows 7 32 位电脑上双击启动一次 `U8Assistant-Win7-x86.exe` 和 `U8诊断工具-Win7-x86.exe`，确认 GUI、PDF 查看、U8 主窗口查找和 ZIP 导出。**

两个 EXE 在 GUI 初始化前立即创建 `%LOCALAPPDATA%\\U8Assistant\\startup.log` 或 `%LOCALAPPDATA%\\U8诊断工具\\startup.log`。日志记录操作系统、架构、内置 Python 版本、EXE 路径和启动阶段；若 GUI 初始化失败，完整异常会记录到该文件，但普通用户界面不会显示 traceback。

## U8Assistant 人工辅助与专用发票半自动模式

`U8Assistant.exe` 默认是人工辅助工具。对已在 Windows 7 x86 新道 U8 “专用采购发票”页面验证过的表头，提供逐项确认的半自动填写；其他业务仍保持人工辅助。

- 左侧任务列表支持任务号、日期、标题、已提取的往来单位/发票号和关键词搜索；“跳到下一个未完成任务”优先定位未标记为“已完成”的任务。
- 中间始终显示任务编号、日期、标题、子任务、PDF 对应页及原始 PDF 页面。页面只按需渲染。
- 右侧“本任务录入数据”只展示 bookmark 和 PDF 原生文本能可靠确认的字段。扫描页无可用文本时，显示“未提取，请查看原始凭证”，且复制按钮保持禁用；不会 OCR 或猜测。
- 复制字段后，切换到 U8 并使用 `Ctrl+V`。快捷键：`Ctrl+C` 重新复制当前已选复制值，`Ctrl+→`/`Ctrl+←` 切换任务，`Ctrl+Enter` 标记任务已完成。快捷键只在 U8Assistant 前台时生效。
- 清单由保守业务分类（采购、销售、收款、付款、库存、固定资产、费用、工资、税务、总账、月末处理、其他/未知）决定。未知任务仅显示“已查看原始凭证 / 待确认”，不会默认要求审核、付款或结算。
- 完成状态和清单勾选保存到本机 `data/progress.json`；打包 EXE 时保存在用户的本地应用数据目录，关闭软件后仍会保留。
- 对采购任务可使用“生成本任务自动录入预览”。它只列出 PDF 原生文本可靠提取的值；扫描页和不确定值不会填写。
- 在“新增”的专用发票页面，点击“检测 U8”后，程序会重新验证页面和供应商弹窗状态。逐项确认后仅可填写开票日期、供应商发票号、税率、币种。供应商选择、明细表格及所有未可靠提取的字段必须手工处理。
- 每次实际填写前都会再次验证当前页面。页面不匹配、字段不唯一、供应商弹窗打开或任何控件访问失败时会立即停止，不继续写后续字段。

### 将原始 PDF 内置到 U8Assistant.exe

为了让普通使用者不用选择或填写 PDF 路径，开发者可在**获授权后**把 `业财税2023.pdf` 放入 `assets/`，再运行 Windows 构建。`U8Assistant.spec` 会自动将它打入 EXE。PDF 默认被 `.gitignore` 排除，避免未经许可上传到 GitHub。未内置时，程序会自动查找 EXE 同目录或 Downloads 中的同名 PDF；找不到时仍可查看任务和进度，但无法显示原始页面。

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

`PyWinAutoU8Controller` 使用经诊断证实的 win32 页面签名与可见标签关系定位“专用采购发票”表头；不会持久化窗口 handle，也不会使用屏幕坐标。其他模块仍没有 U8 专用 selector。业务层只能传递语义化 `ControlTarget`，不能使用屏幕坐标。真实实现必须沿用：Dry Run 默认开启、禁止默认 Save、每步后暂停、任何异常立即停止并记日志，以及用户人工确认才能继续。

本项目不访问 U8 数据库或 SQL Server，不保存账号密码，也不自动保存、记账、审核或结账。

### 专用采购发票：当前验证状态

`src/u8/purchase_invoice_workflow.py` 提供供应商规范化比对、单行 `Decimal` 金额/税额/价税合计校验、结构化失败结果和 Grid capability detection。真实诊断已确认明细控件是 `VSFlexGrid8N` 自绘 Grid，尚未采到可定位的单元格、存货参照或供应商参照 selector。因此程序不会尝试猜测或用绝对坐标填写供应商与明细。

要继续该 workflow 的实机验证，请分别采集以下状态的诊断 ZIP：

1. 新增专用采购发票空白页；
2. 供应商参照弹窗刚打开；
3. 存货参照弹窗刚打开；
4. 第一行数量单元格进入编辑状态；
5. 第一行原币单价单元格进入编辑状态。

这些证据到位后才会启用供应商自动选择和单行 Grid 的键盘/锚点策略；任何 selector 不唯一、回读不一致或意外弹窗都会停止，交由人工处理。

## 项目结构（诊断相关）

```text
u8-assistant/
├── diagnostic_main.py          # U8诊断工具.exe 的 GUI 入口
├── build_windows.bat           # Windows 开发者唯一构建步骤
├── build_win7_x86.bat           # 学校 Win7 x86 发布构建
├── requirements-win7-x86.txt    # Python 3.8 / x86 的锁定二进制依赖
├── U8诊断工具.spec              # PyInstaller one-file/windowed 配置
├── U8Assistant.spec             # 人工辅助 EXE 配置
├── U8Assistant-Win7-x86.spec    # 学校 Win7 x86 的 one-file/windowed 配置
├── U8诊断工具-Win7-x86.spec     # 学校诊断工具的 x86 配置
├── assets/                      # 获授权后可放入待内置 PDF
├── src/
│   ├── gui/diagnostic_window.py
│   └── u8/
│       ├── probe.py             # 只读采集
│       └── diagnostic_bundle.py # 桌面 ZIP 打包
│   └── tasks/
│       ├── business_data.py     # 保守数据/清单模型
│       └── progress.py          # 本地完成状态
└── tests/
```

未来的 `U8Assistant.exe` 也应采用相同原则：终端用户双击程序、在 GUI 中选择任务和确认步骤；Python、pip、日志路径及自动化实现细节均由程序隐藏。本阶段仍未实现任何真实填写功能。
