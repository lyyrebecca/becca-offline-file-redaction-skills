# 从下载到启动：Windows / macOS安装说明

## 你要先知道的四件事

1. 程序本体是本地的，不需要脱敏API Key或付费模型账户。使用Agent时，Agent产品本身的要求另算。
2. 首次安装要联网下载Python依赖和中文模型；日常脱敏可以离线。
3. 目标为 Windows 11 x64 / macOS＋Python3.12，具体已测范围见[验收记录](VERIFICATION.md)。不要求购买 Office；额外 PPT→PDF 才需本机 LibreOffice。不是 iPhone/iPad 程序，不提供内置全部依赖的免安装 exe。
4. 不要把真实原文或口令上传聊天来“帮助安装”。软件复核页面仅在本机使用。

## 方法A：下载ZIP

打开[最新Release](https://github.com/lyyrebecca/becca-offline-file-redaction-skills/releases/latest)，下载`becca-offline-file-redaction-skills-v2.0.1.zip`。解压后进入内部的`legal-privacy-cloak`文件夹，其中应能看到`SKILL.md`、`scripts`和`开始使用.md`。

如果需要校验文件：

```bash
shasum -a 256 becca-offline-file-redaction-skills-v2.0.1.zip
```

与同一Release的`SHA256SUMS.txt`核对。

## 方法B：克隆仓库

```bash
git clone https://github.com/lyyrebecca/becca-offline-file-redaction-skills.git
cd becca-offline-file-redaction-skills
```

两种方法接下来相同。终端必须位于包含`SKILL.md`的项目文件夹；不要直接运行从其他电脑拷来的.app。

## Windows

### 1. 准备一次性依赖

安装 [Python 3.12](https://www.python.org/downloads/)（Windows installer，勾选 Python Launcher 和 Add Python to PATH）。打开独立 PowerShell，执行 `py -3.12 --version`，应显示 Python 3.12。不要在 AI 管理的终端中输入案件口令。

如果电脑已经安装 [Chocolatey](https://chocolatey.org/install)，可在**管理员 PowerShell**安装系统工具：

```powershell
choco install tesseract poppler --no-progress -y
```

若没有 Chocolatey，可按其官方说明安装，或自行使用 [Tesseract Windows分发说明](https://github.com/UB-Mannheim/tesseract/wiki) 和 [Poppler Windows构建](https://github.com/oschwartz10612/poppler-windows/releases) 安装。Poppler的 `Library\bin`、Tesseract的安装目录应加入用户 PATH。Chocolatey 默认目录会被本程序发现；自定义位置需自行加入 PATH。安装完重新打开 PowerShell。

Tesseract 必须同时有 `eng`、`chi_sim`。运行以下命令确认：

```powershell
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs
```

若缺少 `chi_sim`，可从 [Tesseract官方语言数据](https://github.com/tesseract-ocr/tessdata_fast) 下载 `chi_sim.traineddata`，与已有的 `eng.traineddata` 放到用户目录 `\AppData\Local\legal-privacy-cloak\tessdata`，然后设置用户 `TESSDATA_PREFIX`。以下操作仅下载公开模型，**不上传材料**：

```powershell
$data = Join-Path $env:LOCALAPPDATA 'legal-privacy-cloak\tessdata'
New-Item -ItemType Directory -Force $data | Out-Null
Copy-Item 'C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata' $data
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/chi_sim.traineddata' -OutFile "$data\chi_sim.traineddata"
[Environment]::SetEnvironmentVariable('TESSDATA_PREFIX', $data, 'User')
$env:TESSDATA_PREFIX = $data
```

若系统工具安装在自定义位置，请相应修改上述路径。中文模型丢失时程序应报依赖不齐，不能继续当作“已检查”。

### 2. 安装 Skill 和开始菜单入口

解压ZIP后，在 `legal-privacy-cloak` 文件夹的空白处右键“在终端中打开”（或 PowerShell 中 `cd` 到该文件夹），运行：

```powershell
py -3.12 scripts/install.py --with-deps --app
& "$HOME\.codex\skills\legal-privacy-cloak\scripts\run.cmd" doctor
```

看到 `READY` 才表示依赖检查通过。安装器会创建：

- `%LOCALAPPDATA%\legal-privacy-cloak\venv`：本机 Python 运行环境；
- `%USERPROFILE%\.codex\skills\legal-privacy-cloak`：Skill；
- 开始菜单 **贝卡文件脱敏**：带用户指定图标的快捷方式。

随后从开始菜单打开，或双击安装目录中的 **启动贝卡文件脱敏.cmd**。弹出的默认浏览器仅连接本机 `127.0.0.1`；不用登录云端账户。Windows启动器保留控制台供报错；请用网页右上“退出”结束服务。不要把 `.command` 或 `.app` 当作 Windows 启动器。

### 3. 可选PPT转PDF和更新

需要额外像素PDF时安装 [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/)；标准 `Program Files\LibreOffice\program\soffice.exe` 或 PATH 位置会被发现。不勾选该选项则不需要它。

更新前退出服务，备份旧 Skill 目录及开始菜单旧快捷方式，再从新包安装。安装器拒绝静默覆盖。不删除 Documents 里的任务、保险库或恢复件。Windows沿用用户配置目录的 ACL；POSIX `0600` 不等于 Windows ACL，勿把私有目录放进公共共享文件夹。

## macOS：首次安装依赖与桌面入口

先按照[Homebrew官方说明](https://brew.sh/)安装Homebrew，然后在自己打开的终端执行：

```bash
brew install python@3.12 tesseract tesseract-lang poppler
"$(brew --prefix python@3.12)/bin/python3.12" scripts/install.py --with-deps --app
```

它会：

- 建立`~/.local/share/legal-privacy-cloak/venv/`本地运行环境；
- 下载Python依赖和`zh_core_web_sm`中文模型；
- 检查OCR中文/英文语言包与Poppler；
- 安装Skill到`~/.codex/skills/legal-privacy-cloak/`；
- 创建`~/Applications/信息隐身衣.app`；
- 不修改其他Agent配置，不处理任何案件文件。

安装器拒绝覆盖已有目标。没有出现成功结果时，不要当作已安装；`READY`只表示依赖齐备，不代表文件已脱敏。

检查：

```bash
"$HOME/.codex/skills/legal-privacy-cloak/scripts/run.sh" doctor
```

## 启动与退出

Finder中按`Command+Shift+G`，输入`~/Applications/`，双击“信息隐身衣.app”。默认浏览器会打开本机`127.0.0.1`工作台。不是云端网站，不需要先登录AI。

也可双击安装目录中的“信息隐身衣.command”，或者：

```bash
"$HOME/.codex/skills/legal-privacy-cloak/scripts/run.sh" desktop
```

重复打开应用可唤回正在运行的本地服务。用右上“退出”停止服务；只关浏览器标签页不会退出后台。口令只在本地页面输入。

## 可选：PPT额外生成PDF

```bash
brew install --cask libreoffice
```

没有LibreOffice时不要勾选此项；它不是普通PPTX脱敏的必需依赖。PDF扫描件本身的处理使用Poppler和OCR。

## 更新前先备份

退出工作台，备份旧Skill目录和旧启动器后再安装新版本。示例只在本机执行：

```bash
stamp=$(date +%Y%m%d-%H%M%S)
mv "$HOME/.codex/skills/legal-privacy-cloak" "$HOME/.codex/skills/legal-privacy-cloak-backup-$stamp"
# 只有旧app存在时才执行下面一行
mv "$HOME/Applications/信息隐身衣.app" "$HOME/Applications/信息隐身衣-backup-$stamp.app"
```

之后从新项目目录运行安装命令。任务和保险库在Documents下，升级不应删除；口令仍由你独立保管。不要让AI读取备份里的真实映射。

## 安装失败时怎么反馈？

仅提供系统版本、Python版本、`doctor`无原文结果、固定错误码和合成复现方法。不要粘贴真实文件内容、含原文的系统异常、口令或环境凭据。模型/程序缺失不会偷偷切换云端服务。

## 卸载

退出服务后，自行删除Skill安装目录、对应.app；需要时再删除本地运行环境。**不要顺手删除Documents中的加密任务、恢复件或原始文件**，这些是否保留由你决定。
