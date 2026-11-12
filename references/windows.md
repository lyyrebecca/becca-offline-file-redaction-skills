# Windows 使用与故障处理

本版把 Windows 作为正式支持平台：同一套本地引擎在 Windows 10/11、macOS、Linux 上运行，平台差异集中在 `scripts/cloak/platform_support.py`。首次安装仍建议用合成样本走完一遍“导入 → 复核 → 导出 → 恢复”，确认本机界面、OCR 与文件管理器行为符合预期，再处理真实材料。

## 1. 最短上手路径

1. 安装 **Python 3.12**（python.org 官方安装包），安装时勾选 *Add python.exe to PATH*。
2. 把整个技能文件夹放在**不含中文特殊符号、路径较短**的位置，例如 `C:\Tools\信息隐身衣`（也可保留中文目录名，程序本身支持 Unicode 路径）。
3. 打开“命令提示符”，进入该目录：

```bat
cd /d "C:\Tools\信息隐身衣"
py -3.12 scripts\bootstrap.py
scripts\run.cmd doctor
```

4. 之后双击 **信息隐身衣.cmd** 即可打开工作台。也可以创建桌面快捷方式：

```bat
py -3.12 scripts\install.py --shortcut desktop
```

`doctor` 中应看到 `"platform": "Windows"`、`"status": "READY"`，以及 `tool_paths` 里 Tesseract / pdftoppm 的真实位置。

## 2. 中文模型下载被拦截（502 / 超时 / 证书错误）

这通常发生在 GitHub Releases 被代理或网络策略阻断时。程序不会让整个安装失败，而是按以下顺序寻找模型：

| 顺序 | 来源 | 说明 |
|---|---|---|
| 1 | 运行环境已装模型 | 已就绪则完全跳过下载 |
| 2 | `vendor\zh_core_web_sm-3.8.0-py3-none-any.whl` | 手动下载后放进技能目录即可 |
| 3 | 环境变量 `LPC_MODEL_URL` | 指向内部镜像或离线文件服务器 |
| 4 | `requirements-model.txt` 中的官方地址 | 默认 GitHub |
| 5 | 公共 GitHub 代理镜像 | 可用性随时间变化，不保证成功 |

推荐做法：

```bat
rem 方式一：复用本机已装好的 spaCy 3.8 + 中文模型（不下载）
py -3.12 scripts\bootstrap.py --reuse-system

rem 方式二：手动下载 wheel 后从本地安装
py -3.12 scripts\bootstrap.py --wheel "D:\下载\zh_core_web_sm-3.8.0-py3-none-any.whl"

rem 方式三：使用内部镜像
set LPC_MODEL_URL=https://内部镜像/zh_core_web_sm-3.8.0-py3-none-any.whl
py -3.12 scripts\bootstrap.py

rem 方式四：明确接受规则模式（无中文模型，复核时需额外确认）
py -3.12 scripts\bootstrap.py --rule-only
```

`--reuse-system` 会在 `%LOCALAPPDATA%\legal-privacy-cloak\2.4.2\venv` 建立带 `--system-site-packages` 的环境，直接使用系统 Python 中已有的 `spacy 3.8.x` 与 `zh_core_web_sm`。这是网络受限时最稳的路径。

规则模式不是等价替代：它只使用确定性规则、案件词典与表格表头语境，人名、机构名等语义候选可能漏检；工作台会在复核页显示提示，并要求在导出前额外确认该项。

## 3. OCR 与 PDF 工具

| 能力 | 需要 | 常见安装位置（程序会自动探测） |
|---|---|---|
| 图片/扫描件文字识别 | Tesseract 5 + `chi_sim`、`eng` 语言包 | `C:\Program Files\Tesseract-OCR\tesseract.exe`、`%LOCALAPPDATA%\Programs\Tesseract-OCR\` |
| PDF 渲染 | Poppler `pdftoppm` | `C:\Program Files\poppler\Library\bin\pdftoppm.exe`、`C:\poppler\bin\` |
| PPTX 转像素 PDF（可选） | LibreOffice | `C:\Program Files\LibreOffice\program\soffice.exe` |

未加入 PATH 也可以工作。特殊安装位置用环境变量覆盖：

```bat
set LPC_TESSERACT=D:\Tools\tesseract\tesseract.exe
set LPC_PDFTOPPM=D:\Tools\poppler\bin\pdftoppm.exe
set LPC_SOFFICE=D:\Tools\LibreOffice\program\soffice.exe
```

也可把便携版放在技能目录的 `tools\` 或 `vendor\tools\`（支持 `tools\tesseract.exe`、`tools\bin\pdftoppm.exe` 等布局），便于整包搬移。

缺少 Tesseract 或 `chi_sim` 时，涉及图像、扫描 PDF、Office 内嵌图片的材料会**阻断**，不会静默跳过或转交云端。纯文本、CSV、DOCX 文字部分仍可处理。

## 4. 常见报错与处理

| 现象 / 状态 | 原因 | 处理 |
|---|---|---|
| 双击后窗口一闪而过 | 缺少 Python，或未安装本机运行环境 | 用命令提示符运行 `py -3.12 scripts\bootstrap.py`，或运行 `scripts\run.cmd doctor` 看提示 |
| `Python 3.11 or 3.12 was not found` | PATH 中没有匹配版本 | 重装 Python 并勾选 Add to PATH，或 `set LPC_BOOTSTRAP_PYTHON=C:\Python312\python.exe` |
| `LOCAL_NER_UNAVAILABLE` | 没有中文模型，且未接受规则模式 | `--reuse-system`、`--wheel`、`LPC_MODEL_URL`，或 `--rule-only` |
| `TEXT_ENCODING_UNSUPPORTED` | 文本文件是 GBK/ANSI | 用记事本“另存为”UTF-8，再重新导入 |
| `LOCAL_TOOL_UNAVAILABLE` / `LOCAL_TOOL_FAILED` | 未安装或无法启动 Tesseract/Poppler | 见上一节，确认 `doctor` 的 `tool_paths` |
| `FOLDER_OPEN_FAILED` | 系统没有可用的文件管理器句柄 | 复制工作台显示的完整路径，手动粘贴到资源管理器 |
| `PASSPHRASE_MIN_12` | 口令少于 12 字符 | 重新设置；口令遗失无法恢复 |
| 保存保险库失败、权限被拒 | 文件夹受“受控文件夹访问”或同步客户端锁定 | 把任务目录换到其他位置：`set LPC_TASK_HOME=D:\信息隐身衣任务`，再打开工作台 |
| 路径过长（>260 字符） | Windows 传统路径上限 | 把技能目录或任务目录移到较短路径；程序对超长路径使用 `\\?\` 前缀，但第三方工具（Tesseract/Poppler）仍可能受限 |
| 工作台提示“已在运行” | 同一技能目录只允许一个本地服务 | 使用已打开的窗口；或关闭旧窗口后重试 |
| SmartScreen / 杀毒软件提示 | 未签名的脚本与本地服务 | 无需管理员权限；可在“属性”中解除单个文件的锁定，不要全局关闭防护 |
| 端口被占用 / 浏览器未打开 | `127.0.0.1` 随机端口被策略限制 | 查看终端输出的 `http://127.0.0.1:...` 地址手动打开；不要绑定到 `0.0.0.0` |

## 5. 与控制台编码有关的细节

- `scripts\run.cmd`、`信息隐身衣.cmd` 会先执行 `chcp 65001` 并设置 `PYTHONUTF8=1`，Python 端也会强制 UTF-8 输出，因此中文提示不会因 cp936 报 `UnicodeEncodeError`。
- 批处理文件保持纯 ASCII + CRLF：cmd.exe 用 OEM 代码页解析批处理，中文写在 `.cmd` 里容易乱码；所有中文提示都由 Python 输出。
- 终端里如果仍显示方块，请在“命令提示符 → 属性 → 字体”选择“新宋体”或 “Consolas + 中文回退”，不要修改脚本编码。

## 6. 与 macOS/Linux 的差异

- 权限模型：Windows 没有 `chmod`/`fchmod`。加密文件依赖用户目录 ACL 与 NTFS 继承；程序不再调用不存在的 `os.fchmod`，因此保险库写入不会崩溃。
- 时区：Windows 不自带 IANA 时区库，`requirements.txt` 增加了 `tzdata`；同时程序在缺少时回退到固定 UTC+8，任务时间戳不会因此报错。
- 单实例锁：Windows 使用 `msvcrt.locking` 非阻塞锁，第二个实例会尝试聚焦已有窗口，不会卡住 10 秒。
- 打开文件夹：Windows 使用 `os.startfile`，macOS 使用 `open`，Linux 使用 `xdg-open`；界面文案统一为“打开本机文件管理器”。
- 文件选择：向导改用 Tk 原生对话框（三平台一致），不再依赖 AppleScript；没有 Tk 时可粘贴完整路径。

## 7. 交付前自检（合成样本，不接触真实材料）

安装完成后可运行随包自检，覆盖启动器、保险库写入、单实例锁、时区回退、外部工具探测，以及“扫描 → 复核 → 导出 → 残留检查 → 原件恢复”的完整流程：

```bat
py -3.12 tests\run_smoke.py
```

它只在临时目录中生成合成样本，不联网、不读取用户文件，结束后自动清理；加 `--keep` 可保留目录查看结果。缺少 Tesseract/Poppler 时，图像与 PDF 一项会明确标记为跳过，其余步骤仍会执行。全部通过后再处理真实材料。

## 8. 卸载与备份

- 删除软件运行环境：删除 `%LOCALAPPDATA%\legal-privacy-cloak\2.4.2\`。
- **不要**删除任务目录（默认“文档\信息隐身衣任务”或 `LPC_TASK_HOME` 指定目录）中的 `private\task.lpcv`、`share\`、`restored\`，除非用户明确决定。
- 备份时把保险库与口令分开保管；口令遗失没有后门。
