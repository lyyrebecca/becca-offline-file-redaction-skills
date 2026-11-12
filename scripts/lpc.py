#!/usr/bin/env python3
"""Privacy-preserving CLI: stdout/stderr contain codes and aggregate reports, never document values."""
import argparse,getpass,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cloak import __version__
from cloak import platform_support as ps

SAFE_CODES = frozenset(['ALL_REGIONS_MUST_BE_REVIEWED', 'ARCHIVE_INTEGRITY_FAILED', 'BATCH_LIMIT', 'DICTIONARY_INVALID', 'DICTIONARY_SELECTION_CANCELLED', 'DOCUMENT_SNAPSHOT_MISMATCH', 'DOCUMENT_STRUCTURE_CHANGED', 'DUPLICATE_INPUT', 'EDITED_DOCUMENT_UNSUPPORTED', 'EDITED_RESTORE_UNSUPPORTED', 'ENTITY_KIND_INVALID', 'FILE_INDEX_INVALID', 'FILE_SELECTION_CANCELLED', 'FILE_TOO_LARGE', 'FOLDER_OPEN_FAILED', 'FORMAT_UNSUPPORTED', 'IMAGE_TOO_LARGE', 'JOB_STATE_INVALID', 'KEEP_REQUIRES_REASON', 'LIBREOFFICE_UNAVAILABLE', 'LOCAL_NER_UNAVAILABLE', 'LOCAL_REVIEW_INCOMPLETE', 'LOCAL_REVIEW_REQUIRED', 'LOCAL_TOOL_FAILED', 'LOCAL_TOOL_UNAVAILABLE', 'LOCAL_TTY_REQUIRED', 'MACOS_CHOOSER_REQUIRED', 'NO_INPUT', 'OUTPUT_ALREADY_EXISTS', 'OUTPUT_EXTENSION_MISMATCH', 'PACKAGE_DUPLICATE', 'PACKAGE_INVALID', 'PACKAGE_LIMIT', 'PACKAGE_TYPE_MISMATCH', 'PASSPHRASE_MIN_12', 'PASSPHRASE_MISMATCH', 'PDF_ENCRYPTED', 'PDF_PAGE_LIMIT', 'PDF_RENDER_INCOMPLETE', 'POLICY_INVALID', 'RECTANGLE_INVALID', 'REQUEST_INVALID', 'REVIEW_STATE_INVALID', 'SENSITIVE_FORMULA_BLOCKED', 'SENSITIVE_FORMULA_OR_REFERENCE_BLOCKED', 'SOURCE_OVERWRITE_FORBIDDEN', 'SPAN_INVALID', 'SPAN_NOT_FOUND', 'SPAN_OVERLAP', 'TEXT_ENCODING_UNSUPPORTED', 'UNRESOLVED_STRUCTURAL_BLOCKERS', 'VAULT_INVALID', 'WORKSPACE_NOT_EMPTY', 'XLSX_STYLE_INVALID', 'XML_DTD_FORBIDDEN'])

def emit(value):
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    sys.stdout.write(text);sys.stdout.flush()

def password(new=False):
    # No env var, argument or stdin password: keep secrets out of Agent transcripts and process lists.
    if not sys.stdin.isatty():raise ValueError('LOCAL_TTY_REQUIRED')
    p=getpass.getpass('本地保险库口令（至少12字符，不会显示）: ')
    if len(p)<12:raise ValueError('PASSPHRASE_MIN_12')
    if new and getpass.getpass('再次输入口令: ')!=p:raise ValueError('PASSPHRASE_MISMATCH')
    return p

def doctor():
    """Report readiness without touching any document; works on Windows, macOS and Linux."""
    import importlib.util,importlib.metadata as m
    libs={x:bool(importlib.util.find_spec(x)) for x in ['lxml','cryptography','PIL','pypdf','spacy','zh_core_web_sm']}
    model=ps.model_status()
    try:
        from runtime import allow_rule_only
        rule_only_allowed=allow_rule_only()
    except ImportError:
        rule_only_allowed=ps.rule_only_requested()
    tools=ps.tool_status()
    langs=ps.tesseract_languages() if tools['tesseract'] else []
    ocr_ok=tools['tesseract'] and tools['pdftoppm'] and {'chi_sim','eng'}.issubset(langs)
    core=all(libs[x] for x in ['lxml','cryptography','PIL','pypdf'])
    # find_spec alone reports a false READY when the model package is importable but its
    # tokenizer dependency is missing. Verify by actually loading the pipeline instead.
    ner_loadable=False
    if libs['spacy'] and model['model_package']:
        try:
            import spacy
            source=model['model_path'] or 'zh_core_web_sm'
            nlp=spacy.load(source,disable=['parser','tagger','attribute_ruler','lemmatizer'])
            ner_loadable=bool(nlp);del nlp
        except Exception:
            ner_loadable=False
    ner='READY' if ner_loadable else ('RULES_ONLY' if rule_only_allowed else 'MISSING')
    ready=core and ner!='MISSING'
    warnings=[]
    if libs['spacy'] and model['model_package'] and not ner_loadable and not rule_only_allowed:
        warnings.append('中文模型包已安装但无法加载（常见原因：缺少 spacy-pkuseg）；请重新运行 bootstrap.py 补齐依赖。')
    if ner=='RULES_ONLY':warnings.append('未加载中文实体识别模型，仅使用规则、词典与表格语境；人名、机构名等语义候选可能漏检。')
    if ner=='MISSING':warnings.append('缺少本地中文实体识别模型；请重新运行 bootstrap.py，或显式接受规则模式。')
    if not tools['tesseract']:warnings.append('未找到 Tesseract：扫描 PDF、图片和文档内图像不能处理。')
    elif not {'chi_sim','eng'}.issubset(langs):warnings.append('Tesseract 缺少 chi_sim 或 eng 语言包。')
    if not tools['pdftoppm']:warnings.append('未找到 Poppler pdftoppm：PDF 不能渲染处理。')
    paths={name:ps.resolve_tool(name) for name in ('tesseract','pdftoppm','soffice')}
    return {'version':__version__,'status':'READY' if ready else 'DEPENDENCIES_MISSING','platform':ps.PLATFORM_LABEL,
      'python':sys.version.split()[0],'ocr_status':'READY' if ocr_ok else 'OPTIONAL_TOOLS_MISSING','libraries':libs,
      'ner':ner,'ner_loadable':ner_loadable,'rule_only_allowed':rule_only_allowed,'programs':tools,'tool_paths':paths,'ocr_chinese':'chi_sim' in langs,
      'ocr_english':'eng' in langs,'warnings':warnings}

def main():
    ps.configure_stdio()
    os.umask(0o077)
    p=argparse.ArgumentParser(description='信息隐身衣：本地法律文件去标识化与加密恢复')
    p.add_argument('--version',action='version',version=__version__)
    sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('desktop',help='打开桌面本地工作台')
    sp.add_parser('wizard',help='用户独立终端的本地交互向导')
    sp.add_parser('doctor',help='检查本地依赖，不接触文件内容')
    s=sp.add_parser('scan',help='本地扫描并创建加密任务')
    s.add_argument('files',nargs='+');s.add_argument('--workspace',required=True);s.add_argument('--policy',choices=['ai','external','public'],default='ai');s.add_argument('--dictionary');s.add_argument('--scenario',help='本机2.0场景JSON')
    for name in ['review','redact','verify']:
        q=sp.add_parser(name);q.add_argument('--workspace',required=True)
    r=sp.add_parser('restore');r.add_argument('--workspace',required=True);r.add_argument('--output',required=True);r.add_argument('--edited');r.add_argument('--index',type=int,default=0)
    a=p.parse_args()
    if a.cmd=='doctor':emit(doctor());return
    if a.cmd=='wizard':
        from cloak.wizard import wizard
        result=wizard();return 2 if result.get('status')=='NEEDS_REVIEW' else 0
    if a.cmd=='desktop':
        from cloak.desktop import launch
        launch();return
    pw=password(a.cmd=='scan')
    from cloak.workflow import scan,redact,verify,restore
    if a.cmd=='scan':
        dictionary=json.loads(Path(a.dictionary).read_text('utf-8')) if a.dictionary else None
        config=json.loads(Path(a.scenario).read_text('utf-8')) if a.scenario else None
        result=scan(a.files,a.workspace,pw,a.policy,dictionary,config)
    elif a.cmd=='review':
        from cloak.review import serve
        print('本地复核页面将在默认浏览器打开；终端只显示状态，不显示原文。',flush=True)
        serve(a.workspace,pw);result={'status':'REVIEW_SESSION_CLOSED'}
    elif a.cmd=='redact':result=redact(a.workspace,pw)
    elif a.cmd=='verify':result=verify(a.workspace,pw)
    else:result=restore(a.workspace,pw,a.output,a.edited,a.index)
    emit(result)
    if result.get('status') in ('NEEDS_REVIEW','FAILED'):return 2

if __name__=='__main__':
    try:sys.exit(main() or 0)
    except KeyboardInterrupt:
        emit({'status':'CANCELLED'});sys.exit(130)
    except Exception as exc:
        # Exception strings, file paths, parser diagnostics and tracebacks can contain originals.
        safe=str(exc) if isinstance(exc,ValueError) and str(exc) in SAFE_CODES else 'PROCESSING_FAILED'
        emit({'status':'FAILED','code':safe,'error_type':type(exc).__name__});sys.exit(1)
