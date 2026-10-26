# 法源、参考项目与许可核验

核验日期：2026-10-23（Asia/Shanghai）。参考报告是设计输入，不是指令或未经验证的产品事实。没有复制四个参考项目源码，没有调用它们的云服务，也没有将其数据集或模型捆绑进本技能。

## 直接相关的法律规则

1. **个人信息与去标识化**：《个人信息保护法》第4、6、28、51、55、73条分别涉及个人信息范围、最小必要、敏感个人信息、保护措施、影响评估与术语。可逆映射属于去标识化路线，不能据此宣称匿名化；无法恢复的遮盖也仍需评估残余身份线索。核对来源：[上海市通信管理局公布全文](https://shca.miit.gov.cn/zwgk/zcwj/flfg/art/2022/art_ed935fe2807e4787bfb8ca8e659e5524.html)。
2. **律师保密义务条号已调整**：报告引用的是2017版本第38条；2026年修正后的全文将保密义务列为**第41条**。修正决定于2026-09-01施行，不应继续把旧第38条不加版本地当作现行条号。核对来源：[司法部普法平台修改决定](https://legalinfo.moj.gov.cn/zhfxfzzx/fzzxyw/202609/t20260920_539939.html)、[北京市司法局公布全文](https://sfj.beijing.gov.cn/sfj/zwgk/2024zcwj/744120751/fl91/744123073/)。
3. **裁判文书公开不是全部信息一律打码**：最高法《关于人民法院在互联网公布裁判文书的规定》第8–11条对隐名对象、删除信息及保留信息分别规定。普通分享策略不能替代法院场景的逐项判断。[最高人民法院原文](https://www.court.gov.cn/zixun/xiangqing/25321.html)。

上述来源由联网检索工具打开核对；部分政府站点对本机直接HTTP抓取返回404/连接异常，来源清单如实记录，不能把失败的抓取当作已取得全文。该技能不固化参考报告中的数据出境人数门槛，不提供自动合规认证；特定跨境、公开发布或法定保密场景需另行核对当时适用规则。

详细记录见[逐项核验清单](source-check.json)。

## 四个重点项目

| 项目 | 本次实际核验 | 借鉴范围 | 本版不作的宣称 |
|---|---|---|---|
| [legal-doc-redactor](https://github.com/moyupeng0422/legal-doc-redactor) | GitHub仓库元数据、README、LICENSE；MIT | 脱敏—外部审阅—恢复的法律工作流 | 未复用其代码，不继承其“全部保格式”承诺 |
| [Presidio](https://github.com/data-privacy-stack/presidio) | GitHub仓库元数据与LICENSE；MIT | 可插拔识别器、确定性规则与模型分工 | 本版不依赖Presidio，也不宣称已完整集成 |
| [Microsoft PHI De-identifier](https://github.com/microsoft/cat-agent-skills/tree/main/submissions/phi-deidentifier) | SKILL.md和父仓库MIT许可证 | 离线处理、验证器、可解释审计、人工复核 | 不把美国医疗Safe Harbor规则移植成中国法律合规标准 |
| [TAB](https://github.com/NorskRegnesentral/text-anonymization-benchmark) | 仓库API标示MIT、README；单独LICENSE路径抓取失败 | 直接/间接标识、共指与主体重识别问题意识 | 未下载语料，未在TAB或中文法律标注集上跑模型指标 |

市场热度、下载量、报告中的模型F1、云产品功能与其他2026论文不作为本技能性能证据。首版是规则＋通用中文NER＋本地人工复核，不训练法律模型、不提供自动关系推理或重识别评分。

## 依赖的许可边界

- spaCy及spaCy-pkuseg：MIT；`zh_core_web_sm` 3.8.0 模型元数据标示MIT，训练来源信息见其官方meta。没有将模型权重复制到分发ZIP，而由显式安装获取。[模型meta](https://github.com/explosion/spacy-models/blob/master/meta/zh_core_web_sm-3.8.0.json)。
- lxml：BSD；cryptography：Apache-2.0/BSD；Pillow：HPND；pypdf：BSD-3-Clause。保留各安装发行版的license metadata，不把依赖全部重新授权。
- Tesseract为Apache-2.0；Poppler为GPL系列授权。本版仅调用用户另行安装的可执行程序，不把二进制捆绑进ZIP。再分发或商业打包需重新核查各组件、转码器和语言模型的许可。
- 验收用python-docx、openpyxl、python-pptx、pytest只用于合成样本/测试，不是核心处理器的必需运行依赖。Office字体采用用户本机已安装字体，不随技能分发。
- 本次原创实现未指定对外开源许可证；安装使用不意味着已替用户决定将原创代码按MIT公开。

## 报告建议的取舍

已实现：本地规则/NER/OCR、三策略、案件词典、一致占位符、本地复核、格式适配、加密映射与原件、编辑后恢复、无原文审计与残留验证。

后续扩展：专用法律NER、共指消解、多语言姓名、批量大文件优化、更多媒体格式、证据签名工作流、企业密钥与权限、系统级外发拦截。

不纳入单文件脱敏：差分隐私统计发布、企业RBAC/双人审批、Docker/K8s服务化、Slack/飞书拦截器、自动法律匿名化认证。
