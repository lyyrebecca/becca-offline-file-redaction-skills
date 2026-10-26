# 本地运行、安装与恢复

## 用户最短路径

本机安装后，在 Finder 双击技能根目录 **信息隐身衣.command**。2.0 会直接打开四步本地工作台；口令在本机页面输入，文件选择在页面完成。也可双击 `~/Applications/信息隐身衣.app`。旧终端向导保留为 `scripts/run.sh wizard`。没有真实原文或口令需要发到聊天里。

本机已安装的固定入口为 `~/.codex/skills/legal-privacy-cloak/`；实际运行器默认使用 `~/.local/share/legal-privacy-cloak/venv/bin/python`。Windows 使用 `%LOCALAPPDATA%\legal-privacy-cloak\venv\Scripts\python.exe`，启动入口是开始菜单“贝卡文件脱敏”或根目录 `启动贝卡文件脱敏.cmd`。双系统推荐 Python 3.12；完整安装见 [安装说明](../docs/INSTALL.md)，已测范围见 [验收矩阵](../docs/VERIFICATION.md)。Windows 命令示例将 `scripts/run.sh` 换成 `scripts\run.cmd`。

## 依赖安装与离线边界

运行依赖在 `requirements.txt`；`requirements-tested.txt` 记录验收时直接依赖版本。Tesseract、中文/英文语言包、Poppler 的 `pdftoppm` 为外部程序。macOS 可在用户独立终端安装：

```bash
brew install tesseract tesseract-lang poppler
python3.12 scripts/install.py --with-deps --app
```

安装器仅在显式 `--with-deps` 时下载Python依赖与模型；平时 `scan/review/redact/verify/restore` 无云回退、无遥测或模型自动下载。处理期间的网络隔离建议使用操作系统/企业控制；本次V2验收在操作系统沙箱阻断IP网络（仅放行LibreOffice必需的Unix IPC），且验证外部IP连接被拒绝；这不等于已替用户配置整机防火墙。

安装器不自动同步其他Agent，不更改Shell配置；目标存在时拒绝覆盖。卸载时只删除技能目录，运行环境可另行删除；不会自动删除用户加密任务。

## 分步操作

以下命令只在**用户独立打开的本机终端**运行。真实口令不可放进命令行；程序使用隐藏输入。路径示例由用户在本机替换，不把真实词典交给模型。

```bash
# skill目录中的运行器；可先切换到技能目录
scripts/run.sh doctor
scripts/run.sh scan /本地/合同.docx /本地/材料.xlsx --workspace /本地/新任务目录 --policy ai --dictionary /本地/案件词典.json
scripts/run.sh review --workspace /本地/新任务目录
scripts/run.sh redact --workspace /本地/新任务目录
scripts/run.sh verify --workspace /本地/新任务目录

# 取回原件，index从0开始
scripts/run.sh restore --workspace /本地/新任务目录 --index 0 --output /本地/恢复/原件.docx
# 对Office/TXT/MD精确恢复，必须显式给出编辑后的文件
scripts/run.sh restore --workspace /本地/新任务目录 --index 0 --edited /本地/外部审阅稿.docx --output /本地/恢复/审阅恢复稿.docx
```

`scan`要求一个全新/空任务目录。原件快照、绝对路径、完整命中、人工理由、词典和恢复记录只在`private/task.lpcv`中；`scan-report.json`、`audit-report.json`不含这些明文。

口令至少12字符。保险库采用随机16字节salt、scrypt N=32768/r=8/p=1、32字节密钥、AES-256-GCM和随机12字节nonce，格式与AAD绑定。口令遗失无恢复后门；原件应按用户备份策略另行保管。

## 本地复核页面

仅绑定127.0.0.1随机端口，启动时自动打开带一次性引导密钥的本地URL；URL不打印到控制台。会话使用HttpOnly/SameSite=Strict cookie、CSRF字段、Host/Origin检查、CSP、no-store与禁止iframe。旧复核页完成后停止服务；桌面工作台使用右上“退出”停止服务，单独关闭浏览器标签页不会停止后台。

旧复核页逐区保存；2.0 工作台逐文件确认全部区域。对误识别可以取消遮盖但须填写理由，对漏检可补充原文片段，对图片可拖动添加像素矩形。所有有内容的区域与有命中的属性都需检查；没有命中的结构性标记不要求逐项查看。确认图片、身份歧义及跨文件关系后才能批准；不支持的结构无法用勾选消除。

## 输出、状态及异常

- `private/`：加密保险库，权限700/600。不要随脱敏件分享。口令不保存在此目录。
- 旧任务为`share/file-001.ext`；2.0工作台为`share/案件001/类别/file-001.ext`等：中性文件名的候选工作副本及审计报告，不包含源文件名。
- `audit-report.json`：任务、策略版本、类别数量、保留数量、位置索引、规则来源和验证结果；不包含敏感原文、映射或原文裸哈希。
- `verify-report.json`：重新扫描当前输出，输出变更必定回到待复核状态。
- 恢复结果：写到用户指定的新文件，旁边生成不含原文的恢复报告；不会在模型上下文预览。

退出码：0=本次操作正常完成；2=待复核/冲突；1=失败；130=用户取消。`scan`的2是正常的待复核门槛，不要因此绕过流程。文件解析错误只显示固定代码和异常类型，不回传traceback/原文。

残留验证失败：保留待复核状态，根据本地检查补充词典或范围，使用原件在新目录重新扫描；不要手动把报告改成CHECKED。图片OCR误识别也会触发待复核，不能保证所有真实材料一次导出成功。

## 备份与限制

加密保险库与口令分开备份，用户决定保存期限；本版没有自动过期删除、角色权限系统、多人审批、硬件密钥托管或不可篡改企业审计。GCM保护单个保险库完整性，但不能发现整份旧保险库回滚。

本地解密在内存中进行；OCR/PDF临时文件位于权限700临时目录，正常结束会清理。本版不声称防御已控制本机的管理员、内存转储、系统交换分区、异常断电遗留或恶意浏览器扩展。恢复输出与用户选取的原件本身是明文，需由用户本地保管。

## 开发验收（仅合成样本）

使用`requirements-test.txt`安装测试依赖后，可运行`python -m pytest tests -q`和`python tests/run_acceptance.py /新的/验收目录`。后一个程序自己生成虚构文件并自动复核，仅为测试而设，不接受真实输入文件。

独立浏览器保护规则允许标准同源Origin；隔离嵌入浏览器的`Origin:null`仅在`Sec-Fetch-Site:same-origin`、有效会话和CSRF均成立时接受，跨站null来源仍拒绝。

## 2.0补充

`desktop`打开工作台；`scan --scenario /本机/场景.json`可使用2.0场景配置，但案件归属需在工作台打开该任务后确认。无scenario参数仍保持旧CLI平铺输出兼容。默认任务位于`~/Documents/信息隐身衣任务/`。

默认浏览器若有可读页面的扩展，请自行评估并使用可信本机浏览器；软件不控制扩展。界面支持标准文件选择/拖放；自动化扩展没有文件权限时可通过页面的本机路径入口导入，不要求修改浏览器安全设置。

应用启动器不携带全部依赖。另一台电脑应先安装依赖，再运行安装器的`--app`创建当地入口；不要把本机的.app当作跨电脑独立安装包。预览缓存有界，退出清空；异常结束临时目录可能遗留，参见前述本机威胁边界。

应用可重复打开以唤回当前本机工作台；每个端口使用独立会话cookie。原先的浏览器引导链接不能重复使用；本地启动器使用单独的权限600会话描述文件激活现有服务。退出删除该描述文件。
