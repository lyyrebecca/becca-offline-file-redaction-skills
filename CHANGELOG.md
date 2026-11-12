# 变更记录

## 2.4.2 GitHub 发布整理（2026-11-12）

- 同步用户提供的 2.4.2 Windows/macOS 源码；引擎版本保持 2.4.2，不为本次署名和发布文档另设算法版本。
- 制作者统一为李玥滢（lyyrebecca）：Skill、品牌元数据、工作台侧栏与关于页、使用说明和发布检查；不向处理后的法律材料加入署名。
- 修正工作台仍显示 2.2 / 2.2.1 的旧版本号。
- 更新中英文 README、快速开始、安装／升级与常见问题；补充与 GitHub 旧版 2.0.1 的功能差异。旧截图及验收标为历史，不当作新版验收。
- 更新 Windows/macOS CI，安装独立中文模型、执行 Node 交互回归、smoke 与合成多格式验收；固定 Windows 脚本字节换行。
- 保留分层许可及第三方必要声明。

## 2.4.2 — 结构性阻断可解释提示（2026-11-09）

- 交付页在导出前按材料列出结构性阻断、问题代码和中文处理说明；每项可返回相应材料的本机复核页。存在阻断时主操作按钮返回第一份阻断材料，不发送必然失败的导出请求。
- 将软性复核与结构性阻断的分类、中文说明集中到 `scripts/cloak/issues.py`。桌面 `/state` 和 `/review` 返回结构化问题信息；未知代码保留原代码并按结构性阻断失败关闭。
- 覆盖 `UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART`、`UNSUPPORTED_BINARY_PART`、`UNSUPPORTED_XML_TAIL`、`SENSITIVE_FORMULA_BLOCKED`、`SENSITIVE_REFERENCE_BLOCKED`、`SENSITIVE_NUMERIC_WITH_FORMULAS`、`XML_DTD_FORBIDDEN` 和 `MULTIFRAME_IMAGE` 的用户说明。
- `/state` 由后端按当前任务返回实际需要的软性确认项；前端不再复制 `SOFT_ISSUES`。
- 保留 `review_update` 的结构性硬阻断、人工复核、导出、残留验证安全门槛；没有新增忽略阻断或继续导出的选项。`redact` 与 `verify` 的安全逻辑未作修改。
- 更新版本到 2.4.2；更新 Windows/macOS 隔离环境路径、Skill 使用说明、运行说明、发布自检和所需回归测试清单。

### 验收

- 完整 Python 自动化测试：173 passed。
- 合成跨平台 smoke test：10/10 passed（本次实际执行平台：macOS）。
- 合成多格式 acceptance：8 种格式，状态 `CHECKED`；原件字节恢复验证通过。
- Node UI 交互测试验证阻断清单、HTML 转义、逐材料导航、主按钮导航及无阻断时正常导出路径。
- 所有测试仅使用合成材料；没有读取真实案件材料。

## 早期 GitHub 版本

2.0.1 和此前的发布历史见 [2.0.1 Release](https://github.com/lyyrebecca/becca-offline-file-redaction-skills/releases/tag/v2.0.1) 及 [历史验收](docs/VERIFICATION-2.0.1.md)。本文件不推定尚无逐版本记录的中间版本发布日期。
