# macOS 使用与故障处理

macOS 与 Windows 使用同一套本地引擎、同一份复核门槛和同一个自检脚本，差异集中在 `scripts/cloak/platform_support.py`。本页只写 macOS 特有的事项；通用流程见 [运行说明](operations.md)。

## 1. 最短上手路径

支持 macOS 11 及以上（Apple Silicon 与 Intel 均可）。Python 建议使用 python.org 的 3.12 安装包；Homebrew 的 `python@3.12` 也可以。

```bash
cd ~/Downloads/legal-privacy-cloak
python3.12 scripts/bootstrap.py
scripts/run.sh doctor
```

`doctor` 中应看到 `"platform": "macOS"`、`"status": "READY"`、`"ner": "READY"`，以及 `tool_paths` 里 Tesseract / pdftoppm 的实际路径。之后双击 **信息隐身衣.command** 打开工作台，或创建应用：

```bash
python3.12 scripts/install.py --app     # 生成 ~/Applications/信息隐身衣.app
```

应用是启动器，不是自带依赖的独立安装包：它调用技能目录里的 `scripts/run.sh desktop`，技能目录被移动后需要重新生成。启动日志写在 `~/Library/Logs/信息隐身衣.log`，双击没反应时先看这个文件。

## 2. 首次打开被 Gatekeeper 拦下

从网络下载的 zip 会带隔离属性，双击 `.command` 或 `.app` 可能提示“无法打开，因为无法验证开发者”。这属于系统对未签名脚本的常规限制，不需要关闭任何安全功能：

```bash
xattr -dr com.apple.quarantine ~/Downloads/legal-privacy-cloak
chmod +x ~/Downloads/legal-privacy-cloak/scripts/run.sh
chmod +x ~/Downloads/legal-privacy-cloak/信息隐身衣.command
```

如果用的是 tar.gz 包，解压后权限通常已保留，无需 `chmod`。也可以在“系统设置 → 隐私与安全性”里对单个文件选择“仍要打开”。

## 3. 文稿目录授权（TCC）

默认任务目录在 `~/Documents/信息隐身衣任务/`。首次运行时系统会询问“终端（或 Python）想访问‘文稿’文件夹”，必须允许；拒绝后建目录会失败。若不想授权文稿目录，可改用其他位置：

```bash
export LPC_TASK_HOME="$HOME/Library/Application Support/信息隐身衣任务"
scripts/run.sh desktop
```

`LPC_TASK_HOME` 只在当前终端会话生效；希望长期生效，可写进 `~/.zshrc`。

## 4. OCR 与 PDF 工具

```bash
brew install tesseract tesseract-lang poppler
# PPTX 转像素 PDF（可选）
brew install --cask libreoffice
scripts/run.sh doctor
```

程序会自动探测 `/opt/homebrew/bin`、`/usr/local/bin` 与 `/Applications/LibreOffice.app/Contents/MacOS/soffice`。装在非标准位置时用环境变量指定：

```bash
export LPC_TESSERACT=/opt/homebrew/bin/tesseract
export LPC_PDFTOPPM=/opt/homebrew/bin/pdftoppm
export LPC_SOFFICE=/Applications/LibreOffice.app/Contents/MacOS/soffice
```

缺少 `chi_sim` 时，涉及图像、扫描 PDF 和 Office 内嵌图片的材料会被阻断，不会静默跳过或转交云端；纯文本类材料仍可处理。

## 5. Tk 与文件选择

工作台的文件选择走浏览器自己的文件框，不受影响。只有命令行向导 `scripts/run.sh wizard` 使用 Tk 原生对话框：python.org 的安装包自带 Tk，部分 Homebrew Python 缺少 `_tkinter`。

```bash
python3.12 -c "import tkinter; print('tk ok')"
```

如果导入失败，向导会自动退回到“粘贴完整文件路径”的方式，功能不受影响；也可以安装 `brew install python-tk@3.12` 后再试。

## 6. 中文模型下载受限

与 Windows 完全相同的五级兜底：已装模型 → `vendor/` 里的 wheel → `LPC_MODEL_URL` → 官方地址 → 公共镜像。macOS 上常见的是公司网络或代理拦截 GitHub Releases：

```bash
python3.12 scripts/bootstrap.py --reuse-system        # 复用系统已装的 spaCy 与模型
python3.12 scripts/bootstrap.py --wheel ~/Downloads/zh_core_web_sm-3.8.0-py3-none-any.whl
LPC_MODEL_URL=https://内部镜像/zh_core_web_sm-3.8.0-py3-none-any.whl python3.12 scripts/bootstrap.py
```

确实拿不到时用 `--rule-only` 显式接受规则模式：工作台持续提示、`doctor` 报 `ner: RULES_ONLY`、复核清单多一条必须确认的 `RULE_ONLY_DETECTION`。

## 7. 与 Windows 的差异

| 方面 | macOS | Windows |
|---|---|---|
| 启动入口 | 双击 `信息隐身衣.command`，或 `python3.12 scripts/install.py --app` 生成 `.app` | 双击 `信息隐身衣.cmd`，或 `py -3.12 scripts\install.py --shortcut desktop` |
| 文件管理器 | `open`，界面文案“打开本机文件管理器” | `os.startfile`，打开资源管理器 |
| 权限 | POSIX 模式位（`chmod 700/600`），保险库目录仅本人可读 | 目录 ACL 继承；不调用 `fchmod`，改用原子替换 |
| 时区数据 | 系统自带 IANA 数据 | 依赖 `tzdata` 包，缺失时回退固定 UTC+8 |
| 单实例锁 | `fcntl.flock` | `msvcrt.locking` |
| 控制台编码 | 终端默认 UTF-8 | 启动器 `chcp 65001` + Python 强制 UTF-8 |
| 模型与依赖目录 | `~/Library/Application Support/legal-privacy-cloak/2.4.2/` | `%LOCALAPPDATA%\legal-privacy-cloak\2.4.2\` |

## 8. 交付前自检

```bash
python3.12 tests/run_smoke.py
```

只用合成样本、不联网、结束自动清理，覆盖启动器权限、保险库写入、单实例锁、时区、外部工具探测，以及“扫描 → 复核 → 导出 → 残留检查 → 原件恢复”的整条链路；`--keep` 可保留目录。缺少 Tesseract/Poppler 时图像与 PDF 一项标记为跳过，其余照常执行。全部通过后再处理真实材料。
