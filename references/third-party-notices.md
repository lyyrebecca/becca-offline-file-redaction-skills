# 素材与第三方依赖说明

本项目的参考项目、法源与许可证核验记录见 `sources-and-law.md` 和 `source-check.json`。V2 沿用这些来源，不把未核验项目重新宣称为已核验，也不把第三方代码、语料或模型版权改成维护者所有。

本次 V2 新增工作台、场景路由、整理与导出模块为本地实现，不打包下载参考项目的代码。Python 与外部程序通过依赖安装使用，不在 ZIP 中捆绑其运行时或模型。

- lxml：BSD 类许可，按安装发行物携带的许可为准。
- cryptography：Apache-2.0 / BSD-3-Clause 双许可，按所用发行版为准。
- Pillow：HPND，保留其发行许可。
- pypdf：BSD-3-Clause。
- spaCy：MIT；中文模型、spacy-pkuseg 与模型训练数据的声明独立于引擎代码，不能据此对全部训练语料作统一许可承诺。
- Tesseract：Apache-2.0；语言模型随各自发行物。
- Poppler：GPL 系列；作为用户本机外部程序调用，未在本 ZIP 再分发二进制。
- LibreOffice：MPL-2.0 / LGPL 等组件许可；可选本机调用，未在 ZIP 再分发。
- 测试依赖 python-docx、openpyxl、python-pptx、pytest 等的许可随各自安装发行物保留。

`assets/ui-reference.png` 和 `assets/brand-icon.jpg` 为使用者提供的设计素材；缩放后的 PNG / ICNS 仅用于界面与启动器。这里只记录素材来源，不擅自作原创或可商用授权声明。

维护者署名仅属于本项目发布信息，不替换这些依赖或参考项目的作者署名和必须保留的版权声明。
