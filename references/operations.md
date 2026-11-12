# 本地安装、运行、复核与恢复

本版同时支持 **Windows 10/11**、macOS 和 Linux。三者使用同一套 Python 代码；平台差异集中在 `scripts/cloak/platform_support.py`（文件权限、原子写入、文件管理器、外部工具定位、时区、单实例锁、控制台编码）。Windows 细节见 [Windows 说明](windows.md)，macOS 细节见 [macOS 说明](macos.md)。

## 1. 放置 Skill

将完整目录复制到目标 Agent 的 skills 目录，确保 `SKILL.md`、`scripts/`、`assets/`、`references/` 位于该技能目录根部。技能标识为 `legal-privacy-cloak`；若某个 Agent 要求目录名与元数据名称一致，将文件夹重命名为该标识即可。此 Skill 不依赖特定电脑的用户目录、旧 venv、旧系统模型或既有任务目录。

## 2. 新电脑首次安装

需要 Python 3.11 或 3.12。首次安装 Python 依赖需要联网访问 PyPI；中文 spaCy 模型可另行获取。安装前应由用户明确同意联网。不要把原始法律文件交给安装器，也不要在安装步骤中打开任何材料。

### Windows

在本机“命令提示符”或 PowerShell 中进入技能目录（路径含空格时加引号）：

```bat
py -3.12 scripts\bootstrap.py
scripts\run.cmd doctor
```

没有 `py` 启动器时改用 `python scripts\bootstrap.py`。也可以直接双击技能目录的 **信息隐身衣.cmd** 打开工作台（首次会自动提示先安装依赖）。默认运行时位于 `%LOCALAPPDATA%\legal-privacy-cloak\2.4.2\venv\`。

### macOS / Linux

```bash
python3.12 scripts/bootstrap.py
scripts/run.sh doctor
```

若电脑只有 Python 3.11，使用 `python3.11`。macOS 可用 `信息隐身衣.command` 打开工作台，`python3.12 scripts/install.py --app` 在 `~/Applications/` 创建 `.app`；Windows 可用 `python scripts\install.py --shortcut desktop` 创建桌面快捷方式；Linux 用 `python3.12 scripts/install.py --shortcut` 创建应用菜单项。

`bootstrap.py` 只根据本目录的 `requirements.txt` 创建该版本专用 venv、安装 Python 包、获取中文模型并验证环境，不读取用户文档。不同版本使用独立目录，不会寻找或复制旧电脑上的 venv。

### 中文模型获取顺序

Windows 上最常见的问题是无法访问 GitHub Releases。程序按以下顺序尝试，任何一步成功即停止：

1. 当前环境已能 `import zh_core_web_sm`；
2. 技能目录 `vendor/` 下的 `zh_core_web_sm-3.8.0-py3-none-any.whl`（可用 `--wheel` 指定其他位置）；
3. 环境变量 `LPC_MODEL_URL`；
4. `requirements-model.txt` 中的官方地址；
5. 公共 GitHub 代理镜像（可用性随时间变化，不作为成功保证）。

若本机 Python 已装好 spaCy 3.8 与中文模型，程序会自动改用 `--system-site-packages` 创建环境并**完全跳过下载**；也可显式运行：

```bat
py -3.12 scripts\bootstrap.py --reuse-system
```

全部渠道都失败时，程序不会静默降级。用户可选择显式接受规则模式：

```bat
py -3.12 scripts\bootstrap.py --rule-only
```

该模式只使用规则、词典与表格语境，不加载中文模型；工作台会持续显示提示，并在复核清单中增加一项必须确认的说明。`doctor` 中 `ner` 显示 `RULES_ONLY`。需要语义识别时应补齐模型，不要把它当作等同能力。

## 3. OCR/PDF 系统工具

Tesseract、`chi_sim`/`eng` 语言数据、Poppler `pdftoppm` 和（可选的）LibreOffice 不是 Python 包，不会由 bootstrap 静默安装。缺少它们时，纯文本类格式仍可运行；涉及图像、扫描 PDF 或 PPTX 转 PDF 的部分必须停止并明确报告，不静默跳过、不回退云端。

- Windows：安装 Tesseract 5（勾选 Chinese (Simplified) 语言包）与 Poppler；即使没有加入 PATH，程序也会检查 `C:\Program Files\Tesseract-OCR`、`%LOCALAPPDATA%\Programs\Tesseract-OCR`、`C:\Program Files\poppler\Library\bin` 等常见位置。也可把便携版放进技能目录的 `tools\` 或 `vendor\tools\`，或用环境变量 `LPC_TESSERACT`、`LPC_PDFTOPPM`、`LPC_SOFFICE` 指定完整路径。
- macOS：`brew install tesseract tesseract-lang poppler`。
- Linux：`sudo apt install tesseract-ocr tesseract-ocr-chi-sim poppler-utils`。

`doctor` 的 `status: READY` 表示 Python 依赖与识别模式可用（含显式规则模式）；`ocr_status: READY` 才表示 OCR/PDF 外部工具和语言包齐备。`tool_paths` 会给出程序实际使用的可执行文件位置，便于排查“装了但找不到”。

## 4. 常规运行命令

以下命令应由用户在本机独立打开的终端执行。不要让 Agent 在 PTY 中代输真实保险库口令。CLI 的口令仅通过本机 TTY 的隐藏输入取得；禁止放在参数、环境变量或 stdin 管道中。

Windows（命令提示符）：

```bat
scripts\run.cmd doctor
scripts\run.cmd scan "C:\材料\起诉状.docx" --workspace "C:\新任务目录" --policy ai
scripts\run.cmd review --workspace "C:\新任务目录"
scripts\run.cmd redact --workspace "C:\新任务目录"
scripts\run.cmd verify --workspace "C:\新任务目录"
scripts\run.cmd restore --workspace "C:\新任务目录" --index 0 --output "C:\恢复\原件.docx"
```

PowerShell 使用 `powershell -ExecutionPolicy Bypass -File scripts\run.ps1 doctor`，macOS/Linux 使用 `scripts/run.sh ...`。新电脑首次使用前启动器不会偷偷安装软件；若尚无 venv，会提示先运行 `bootstrap.py`。扫描要求新的空任务目录。工作台的口令字段只在 127.0.0.1 本地会话输入。保险库口令至少 12 个字符；丢失后无恢复后门。

## 5. 数据位置与复核要求

默认任务目录：Windows 为“文档”库下的 `信息隐身衣任务\`（OneDrive 重定向时跟随系统“文档”位置），macOS/Linux 为 `~/Documents/信息隐身衣任务/`。`private/` 保存加密任务、原件快照和映射；`share/` 仅含候选脱敏副本和不含敏感原文的报告；`restored/` 是用户明确请求的恢复件。不要分享整个任务目录。用户选取的原件、恢复输出和学习库仍是本机敏感数据。

工作台中的每批默认统一归入一个案件编号，不要求逐文件确认案件/类别；多个案件应分开建任务。每个文件仍必须逐份复核。可拖选文本补漏并按用户确认将同字面项传播到本批；连续数字/编码候选默认不打码，需逐项决定。右键取消单条候选需二次确认，并使相关文件重新复核。图片位置标签可跳转命中或移除手工遮挡。精确学习规则可使用本机任务口令加密保存；未来同口令任务才会载入，不学习语义，也不跨案件推断。

`NEEDS_REVIEW` 表示未完成，不是通过。残留、冲突、不可审阅结构或文件导出后变化均需保留待复核状态。`CHECKED` 只说明本次机械检查和人工复核门槛通过，不是零漏检保证、法律授权或匿名化认证。

交付页会在导出前读取本机后端提供的结构化阻断列表，逐项显示受影响材料、问题代码和处理说明；“返回此材料”直接进入该材料的本机复核页。存在阻断时主操作按钮会返回第一份阻断材料。页面上的三项人工确认只用于软性人工复核，不能覆盖或解除结构性阻断；不存在忽略阻断并继续导出的选项。遇到阻断应按说明在本机制作可完整检查的静态副本，再重新导入；不要尝试绕过检查。未知问题代码也会保留显示，并附通用的失败关闭说明。

## 6. 格式边界

支持白名单包括 DOCX/XLSX/PPTX、PDF、PNG/JPEG、UTF-8 TXT/Markdown、CSV/TSV、JSON/XML、LOG 和受限的单段 `text/plain` EML。EML 可解码 MIME Base64/quoted-printable；多段、HTML 和附件邮件阻断，输出是不可直接发送的 `X-LPC-*` 复核副本。未知格式和不安全结构失败关闭。OCR/PDF 工具缺失时，不允许将文件当成无敏感内容继续。

文本类文件必须是 UTF-8（可带 BOM）。Windows 上用记事本“另存为 ANSI/GBK”的文件会以 `TEXT_ENCODING_UNSUPPORTED` 阻断，程序不猜测编码，也不会把乱码当成无敏感内容。

## 7. 安装器与选项

- `bootstrap.py`：创建/验证本版本用户级运行环境，不复制 Skill，也不处理文件。
- `bootstrap.py --refresh`：按本目录 `requirements.txt` 重新安装依赖。
- `bootstrap.py --reuse-system`：复用系统 Python 中已装的 spaCy 与中文模型，网络受限时推荐。
- `bootstrap.py --rule-only`：显式接受无中文模型的规则模式（复核时需额外确认）。
- `bootstrap.py --wheel 路径.whl`：从本机 wheel 安装中文模型，可重复。
- `bootstrap.py --model-url 地址`：自定义模型下载地址，可重复。
- `bootstrap.py --index-url 地址`：自定义 PyPI 源，可重复；默认在官方源失败后尝试国内镜像。
- `install.py --with-deps`：执行 bootstrap。
- `install.py --target <空的Agent技能目录>`：可选复制当前 Skill；目标已存在会拒绝覆盖。
- `install.py --app`：仅 macOS，在依赖就绪后创建 `.app`；现有应用不会自动覆盖。
- `install.py --shortcut desktop|startmenu`：Windows 创建 `.lnk` 快捷方式，Linux 创建应用菜单项。

卸载运行环境时仅删除本机 `legal-privacy-cloak/2.4.2/` 软件运行目录；不要误删任务目录中的任务、保险库或恢复文件。备份和删除任务由用户自行决定。
