"""Authoritative issue catalog shared by workflow, desktop API and review views."""
from __future__ import annotations

SOFT_ISSUES = frozenset({
    'IMAGE_VISUAL_REVIEW',
    'CROSS_FILE_IDENTITY_REVIEW',
    'ENTITY_AMBIGUITY_REVIEW',
    'EML_HEADERS_NORMALIZED',
    'RULE_ONLY_DETECTION',
})

SOFT_ISSUE_MESSAGES = {
    'IMAGE_VISUAL_REVIEW': '请在本机逐图检查扫描页、图片与遮挡预览，并补充签名、人脸、二维码等可能漏检区域。',
    'CROSS_FILE_IDENTITY_REVIEW': '请人工核对跨文件身份关系；系统不会仅凭同名自动合并主体。',
    'ENTITY_AMBIGUITY_REVIEW': '请人工核对同名主体、别称、间接身份线索，以及必须保留的法律细节。',
    'EML_HEADERS_NORMALIZED': '邮件头已按复核格式整理；请检查展示的发件人、收件人、主题、日期及正文。',
    'RULE_ONLY_DETECTION': '本次未加载中文实体识别模型，仅使用规则、词典与表格语境；请额外检查人名、机构名等语义候选。',
}

STRUCTURAL_BLOCKER_MESSAGES = {
    'UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART': '材料含暂不支持的嵌入对象、动态数据、自定义内容或数字签名。请在本机制作移除这些结构的静态副本，再重新导入。',
    'UNSUPPORTED_BINARY_PART': '材料含当前版本无法安全解析的二进制部件。请在本机移除该部件或另存为受支持的静态格式，再重新导入。',
    'UNSUPPORTED_XML_TAIL': '材料的 XML 结束标记后仍有额外内容，本工具无法完整检查。请用本机办公软件另存为干净副本，再重新导入。',
    'SENSITIVE_FORMULA_BLOCKED': '公式或公式缓存中检测到可能需要隐藏的信息；直接替换可能破坏计算关系。请先在本机核查公式依赖，并制作安全副本。',
    'SENSITIVE_REFERENCE_BLOCKED': '工作表名、命名区域、引用或包路径中检测到敏感文字；直接改名可能破坏文档关系。请先在本机处理相关引用并重新导入。',
    'SENSITIVE_NUMERIC_WITH_FORMULAS': '检测到数字型敏感信息，同时工作簿含公式。修改该数字可能改变计算结果；请先在本机确认依赖并制作安全副本。',
    'XML_DTD_FORBIDDEN': '材料含 XML 文档类型定义（DTD），可能引用外部实体或资源。为安全起见，本工具拒绝解析；请在本机另存为不含 DTD 的副本。',
    'MULTIFRAME_IMAGE': '图片含多帧或多页，而当前处理无法逐帧完成检查。请在本机拆分为单帧图片、逐帧复核后重新导入。',
    'DYNAMIC_FIELD_REVIEW': '材料含可刷新或动态域；请在本机将其转换为静态文本后重新导入。',
    'EXTERNAL_DEPENDENCY': '材料依赖外部文件、工作簿或数据源；请在本机解除外部依赖后重新导入。',
    'SENSITIVE_FORMULA_OR_REFERENCE_BLOCKED': '公式或文档引用中含敏感内容；直接替换可能破坏计算或引用关系。请先在本机核查并制作安全副本。',
}

GENERIC_STRUCTURAL_BLOCKER_MESSAGE = (
    '该材料含当前版本尚不能安全检查或处理的结构，不能跳过。请依据问题代码在本机制作静态安全副本后重新导入；'
    '如无法确认结构安全，请停止交付。'
)


def describe_issue(code: str) -> dict[str, str]:
    """Return a display-safe, structured description; unknown codes fail closed."""
    code = str(code)
    if code in SOFT_ISSUES:
        return {
            'code': code,
            'severity': 'soft',
            'message': SOFT_ISSUE_MESSAGES.get(code, '需要完成本机人工复核。'),
        }
    return {
        'code': code,
        'severity': 'structural',
        'message': STRUCTURAL_BLOCKER_MESSAGES.get(code, GENERIC_STRUCTURAL_BLOCKER_MESSAGE),
    }


def issue_details(codes) -> list[dict[str, str]]:
    """Describe unique codes without duplicating classification rules in a UI."""
    return [describe_issue(code) for code in sorted({str(code) for code in codes})]


def required_soft_confirmations(files) -> list[str]:
    """Return only soft-review codes actually present in this task's files."""
    return sorted({
        str(code)
        for record in files
        for code in record.get('issues', [])
        if str(code) in SOFT_ISSUES
    })


def structural_blockers(files) -> list[dict[str, object]]:
    """Create per-file blocker records for local UI/API display, not for policy decisions."""
    result = []
    for index, record in enumerate(files):
        source = str(record.get('source') or '')
        name = str(record.get('local_label') or source.replace('\\', '/').rsplit('/', 1)[-1] or f'材料 {index + 1}')
        for detail in issue_details(record.get('issues', [])):
            if detail['severity'] != 'structural':
                continue
            result.append({
                'file_index': index,
                'file_name': name,
                'code': detail['code'],
                'message': detail['message'],
            })
    return result
