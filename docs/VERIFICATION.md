# 验收记录：哪些能力实际测过？

本页区分“历史2.0.0阶段”“2.0.1发布前本地复验”和“GitHub自动化”，不把旧结论自动当作新版本完成。

日期：2026-10-26。所有样本为程序生成的虚构数据。公开截图是工作台实际运行页面，不是概念图；原始案件、保险库、映射和恢复内容不进入仓库。

## 2.0.1本地重新验收

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 全量回归 | **96 passed**，112.04秒 | [本地测试摘要](evidence/local-tests.txt) |
| 乱序8格式端到端 | 冷暖两轮均CHECKED | [断网验收摘要](evidence/offline-acceptance.json) |
| 原件恢复 | 两轮共16份，均按字节相同 | 同上 |
| AI辅助文件 | 每轮8份Markdown＋2份索引，复查通过 | 同上 |
| 学生课件清理 | 删除1张隐藏页，清理备注/私有关系及孤立部件 | 同上及回归 |
| 可选PPT像素PDF | 输出1页，无可提取原文字层，残留检查通过 | 同上 |
| 外部IP阻断 | OS沙箱deny network*；仅本机Unix IPC放行；主动IP连接探针被拒绝 | 同上 |
| Skill、包结构与发布排除项 | 发布检查脚本检查 | `python scripts/check_release.py` |
| 发布版真实UI | 见下方截图、操作清单与摘要 | [UI摘要](evidence/ui-acceptance.json) |
| GitHub自动测试 | 以对应提交的实际Actions状态为准，不凭README写成功 | [Actions](https://github.com/lyyrebecca/becca-offline-file-redaction-skills/actions) |

## 实测速度

小型8格式合成批次，排除人工复核：

| 阶段 | 冷轮 | 同进程暖轮 |
|---|---:|---:|
| 扫描 | 4.856秒 | 1.668秒 |
| 导出＋Markdown＋内置检查 | 4.889秒 | 3.419秒 |
| 两阶段合计 | **9.745秒** | **5.087秒** |

学生课件单独含可选像素PDF的流程约10.664秒。环境为Apple Silicon arm64、macOS26.6.2。数字只说明这组样本，不是对任意长文档/大扫描件的承诺。正文处理不请求外部LLM，日常与Agent的聊天开销另算。

## 真实操作截图与复核路径

1. 从正式发布版页面选择学生分发场景，额外开启Markdown；保存[场景页](screenshots/01-workbench.png)。
2. 实际通过本机路径入口导入3份合成DOCX/PPTX/PNG。识别后编辑待确认图片的案件归属，保存[分类页](screenshots/02-classification.png)。
3. 按文件复核合成文字与课件；检查学生清理统计和原图/遮挡预览，在PNG上拖动添加手工黑块，保存[图像页](screenshots/03-image-review.png)。
4. 完成逐文件和最终确认，执行真实导出/verify；保存[结果页](screenshots/04-delivery.png)。点击文件夹入口和复制路径，检查本机打开结果；保存恢复/作者说明的补充截图。
5. 公开页面路径使用独立`/tmp/becca-redaction-public-demo/`合成工作区，不曝光开发者的个人课程目录或真实案件路径。公开截图不修改界面中的结果数字或伪造遮挡。

截图证明所展示的交互与页面状态；全文格式覆盖、加密、恢复和安全场景还由自动测试与断网验收共同证明，不能只靠截图断言“零漏检”。自动文件选择器填充受本机Chrome扩展权限影响，实际UI使用已完成测试的本机路径入口；未通过改浏览器权限来掩盖此限制。

## 如何复现

本机准备运行依赖及OCR后：

```bash
python3.12 -m pip install -r requirements.txt -r requirements-test.txt
python3.12 -m pytest tests -q
python3.12 scripts/check_release.py
```

完整OS断网验收仅面向macOS，并需要可选LibreOffice已安装；目录必须全新：

```bash
sandbox-exec -p '(version 1)(allow default)(deny network*)(allow network* (local unix-socket) (remote unix-socket))' \
  python3.12 tests/run_acceptance_v2.py /tmp/becca-redaction-acceptance-new
```

程序自己生成合成材料并模拟复核，**不能把它改为真实文件的自动批准器**。普通真实文件必须由使用者在本机完成复核。

GitHub工作流执行模型/OCR依赖准备、发布结构与前端语法检查、96项合成回归。它不声称代替GUI截图、OS沙箱验收或可选LibreOffice渲染；这三类证据应分开阅读。

## 历史验收与限制

[2.0.0历史阶段报告](../发行验收报告.md)记录了当时的安装、实际Office打开/渲染及编辑恢复。2.0.1保留核心算法与保险库格式，另完成上述重新回归和实际页面复验。

不能由本次测试推出：真实案件零漏检、所有页完美保真、任意平台可用、自动识别人脸/二维码、语义并案、自动拆分多案文档或法律匿名化认证。重要文件仍须本机实际打开，确认条款、金额日期、分页与画布内容。
