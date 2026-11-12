# 安装、升级与卸载 · 2.4.2

制作者：李玥滢（lyyrebecca）。支持 Windows 10/11 与 macOS；Python 3.11/3.12，推荐 3.12。不是自带全部依赖的免安装软件。

## 下载与目录

从[发布页](https://github.com/lyyrebecca/becca-offline-file-redaction-skills/releases/latest)选择 `legal-privacy-cloak-2.4.2.zip`。解压后 `legal-privacy-cloak/` 根部应直接看到 `SKILL.md`、`scripts/`、`assets/`、`references/` 和启动器。

GitHub 自动生成的 Source code 包是仓库快照，目录名不同；使用命令前须进入实际包含 `SKILL.md` 的目录。源码用户也可克隆本仓库，直接在根目录运行。

## Windows

本机安装 Python 3.12（含 `py` 启动器），在技能目录运行：

```powershell
py -3.12 scripts\bootstrap.py
scripts\run.cmd doctor
```

双击 `信息隐身衣.cmd`。可选快捷方式：

```powershell
py -3.12 scripts\install.py --shortcut desktop
# 或开始菜单
py -3.12 scripts\install.py --shortcut startmenu
```

`--app` 仅用于 macOS，Windows 不使用该参数。没有 `py` 时使用已安装的兼容版本 `python`。

OCR/PDF 需要 Tesseract 5（`chi_sim`、`eng`）与 Poppler；程序探测常见目录，也可通过 `LPC_TESSERACT`、`LPC_PDFTOPPM` 指定。详见[Windows 说明](../references/windows.md)。

## macOS

安装 Python 3.12 后：

```bash
python3.12 scripts/bootstrap.py
chmod +x scripts/run.sh 信息隐身衣.command
scripts/run.sh doctor
python3.12 scripts/install.py --app
```

双击 `.command` 或打开 `~/Applications/信息隐身衣.app`。`.app` 仍依赖技能目录与本机环境；移动源码后需要重新生成。旧应用存在时安装器拒绝覆盖。

若已安装 Homebrew，OCR/PDF 可通过以下方式准备：

```bash
brew install tesseract tesseract-lang poppler
# 仅需要 PPTX 转像素 PDF 时安装
brew install --cask libreoffice
```

解压权限、Gatekeeper 单文件允许、文稿目录授权及日志排查见[macOS 说明](../references/macos.md)。不需要关闭整机安全设置。

## 模型下载与规则模式

Bootstrap 创建版本隔离的用户环境；不读取材料，不在启动时静默安装。中文模型从已安装环境、本地 wheel、自定义地址与官方/备用渠道尝试获取。

```text
scripts/bootstrap.py --reuse-system
scripts/bootstrap.py --wheel /本机路径/zh_core_web_sm-3.8.0-py3-none-any.whl
scripts/bootstrap.py --rule-only
```

以上参数需加上本机 Python 命令。`--reuse-system` 适合相应 Python 已有模型的情况。`--rule-only` 必须由使用者明确接受，界面持续提示且需额外复核；不能宣称等同模型模式。第三方下载源有自身可用性和信任边界；可自行准备官方 wheel。

`doctor` 的 `status: READY` 表示核心环境与所选识别模式就绪；`ocr_status: READY` 才说明 OCR/PDF 工具及语言数据齐备。缺少图像依赖时不能将图像当成无敏感内容通过。

## Codex 安装

将完整技能目录复制到 `~/.codex/skills/legal-privacy-cloak`（Windows 通常为 `%USERPROFILE%\.codex\skills\legal-privacy-cloak`），或用 `scripts/install.py --target <尚不存在的技能目录>`。依赖未就绪时先 bootstrap。调用 `$legal-privacy-cloak`。

## 升级

- 备份旧技能目录和仍需使用的任务；新版解压到新位置，不覆盖仍在运行的旧会话。
- 2.4.2 使用自己的运行环境：Mac 为 `~/Library/Application Support/legal-privacy-cloak/2.4.2/`，Windows 为 `%LOCALAPPDATA%\legal-privacy-cloak\2.4.2\`。
- 不复制旧 venv；使用新版 bootstrap 验证依赖，并重新创建指向新版的启动器。
- 不承诺任意历史任务或编辑副本可跨版本恢复。历史任务保留原版本与口令；新版用合成副本确认流程后再处理新任务。
- 默认任务根目录可能复用本机学习库；同口令才载入精确词条，不自动解锁或迁移口令。

## 卸载

移除 Skill、启动器／快捷方式及对应版本运行目录。任务默认保存在系统“文档”中的 `信息隐身衣任务`；它们不是可随意清理的软件缓存。原件、保险库、学习库和恢复件由用户另行备份或删除。

更多命令、数据位置、恢复与限制见[运行说明](../references/operations.md)。
