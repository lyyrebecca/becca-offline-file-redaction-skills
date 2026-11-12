# 2.4.2 验收范围

发布整理日期：2026-11-12。制作者：李玥滢（lyyrebecca）。本轮仅使用程序生成的合成材料，不读取真实案件。

## 本次本机复验

| 项目 | 结果与范围 |
|---|---|
| 平台 | macOS arm64，Python 3.12.14；不是 Windows 实体桌面 |
| 原版新增功能及完整 Python 回归 | **180 passed**（新版原有 173 项＋保留旧仓库修复的 7 项集成回归）；含结构性阻断目录、后端状态、候选、格式、恢复与跨平台适配回归 |
| Node 交互测试 | **PASS**：阻断清单、HTML 转义、逐材料导航、主按钮返回、无阻断正常导出路径 |
| 发布自检 | 检查 Python 语法、包内链接、必需文件、版本与个人署名、Windows CRLF/ASCII、阻断与前后端协议 |
| Smoke | **10/10 PASS**；含中文空格路径、启动器、锁、文本／Office／图像与 PDF 流程 |
| 合成多格式端到端 | **8 格式 CHECKED**；8 份原件恢复字节一致 |

2.4.2 源码原有 CHANGELOG 的 173 项验收及新增的 7 项集成回归均已在本机重新执行；不是直接引用附件报告作为当前通过证明。Node 测试执行的是精简交互测试环境，不等同真实浏览器全流程点击或所有页面视觉验收。

本机摘要：[2.4.2 合成验收记录](evidence/2.4.2-local.json)。

## 原生 CI 与人工验收分开看

[Windows / macOS 工作流](https://github.com/lyyrebecca/becca-offline-file-redaction-skills/actions/workflows/ci.yml)在两种原生 runner 上安装模型及 OCR，执行发布自检、Node 交互测试、smoke、合成多格式端到端与 Python 回归。以 **2.4.2 对应提交**的实际结果为准，不把旧版绿色徽章当作新版已通过。

- Windows runner 不是实体 Windows 10/11 普通用户桌面；不证明人工文件选择、中文输入法、Office 打开或排版均已验收。
- 本轮 macOS 自动复验不是新增全页截图验收；README 图像明确保留为 2.0.1 历史演示。
- 本轮常规自动测试没有施加 OS 网络封锁，不宣称重复完成旧版的系统级断网验收。
- Linux 有代码路径适配，但本轮 CI 未覆盖 Linux，也没有手机／平板版本。

## 复现

准备 Python 3.11/3.12、中文模型、Tesseract（chi_sim＋eng）及 Poppler 后，在项目根目录运行：

```bash
python3.12 -m pip install -r requirements.txt -r requirements-model.txt -r requirements-test.txt
python3.12 scripts/check_release.py
python3.12 -m pytest tests -q
node --check assets/ui/app.js
node tests/test_delivery_ui.js assets/ui/app.js
python3.12 tests/run_smoke.py
python3.12 tests/run_acceptance.py /本机全新目录/合成验收
python3.12 scripts/build_release.py
```

Windows 将 `python3.12` 换为 `py -3.12`。测试会生成合成原件、保险库与恢复件；公开证据只保留摘要，不上传整份任务目录。不能把测试中的模拟批准改为真实材料的自动批准器。

## 历史证据

[2.0.1 历史验收](VERIFICATION-2.0.1.md)与[更早阶段报告](../发行验收报告.md)保留原时间与版本，供追溯。历史断网、截图与速度结论不自动延伸到 2.4.2。

`CHECKED` 不是实际材料零漏检、任意格式完全保真、披露合法性或法律匿名化认证；真实文件仍需使用者本机逐份审阅。
