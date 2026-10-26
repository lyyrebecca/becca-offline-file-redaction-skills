# 从下载到启动：Mac安装说明

## 你要先知道的四件事

1. 程序本体是本地的，不需要脱敏API Key或付费模型账户。使用Agent时，Agent产品本身的要求另算。
2. 首次安装要联网下载Python依赖和中文模型；日常脱敏可以离线。
3. 正式验收桌面环境为macOS＋Python3.12。不是Windows安装器，不要求购买Office，额外PPT→PDF才需本机LibreOffice。
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

## 首次安装依赖与桌面入口

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
