#!/usr/bin/env python3
"""Privacy-preserving CLI: stdout/stderr contain codes and aggregate reports, never document values."""
import argparse,getpass,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cloak import __version__
from cloak.platforms import prepare_tools
prepare_tools()

SAFE_CODES = frozenset(['ALL_REGIONS_MUST_BE_REVIEWED', 'ARCHIVE_INTEGRITY_FAILED', 'DICTIONARY_INVALID', 'DICTIONARY_SELECTION_CANCELLED', 'DOCUMENT_SNAPSHOT_MISMATCH', 'DOCUMENT_STRUCTURE_CHANGED', 'DUPLICATE_INPUT', 'EDITED_DOCUMENT_UNSUPPORTED', 'EDITED_RESTORE_UNSUPPORTED', 'ENTITY_KIND_INVALID', 'FILE_INDEX_INVALID', 'FILE_SELECTION_CANCELLED', 'FILE_TOO_LARGE', 'FORMAT_UNSUPPORTED', 'IMAGE_TOO_LARGE', 'JOB_STATE_INVALID', 'KEEP_REQUIRES_REASON', 'LOCAL_NER_UNAVAILABLE', 'LOCAL_REVIEW_INCOMPLETE', 'LOCAL_REVIEW_REQUIRED', 'LOCAL_TOOL_FAILED', 'LOCAL_TOOL_UNAVAILABLE', 'LOCAL_TTY_REQUIRED', 'MACOS_CHOOSER_REQUIRED', 'NO_INPUT', 'OCR_OUTPUT_INVALID', 'OUTPUT_ALREADY_EXISTS', 'OUTPUT_EXTENSION_MISMATCH', 'PACKAGE_DUPLICATE', 'PACKAGE_INVALID', 'PACKAGE_LIMIT', 'PACKAGE_TYPE_MISMATCH', 'PASSPHRASE_MIN_12', 'PASSPHRASE_MISMATCH', 'PDF_ENCRYPTED', 'PDF_PAGE_LIMIT', 'PDF_RENDER_INCOMPLETE', 'POLICY_INVALID', 'RECTANGLE_INVALID', 'REQUEST_INVALID', 'REVIEW_STATE_INVALID', 'SENSITIVE_FORMULA_BLOCKED', 'SENSITIVE_FORMULA_OR_REFERENCE_BLOCKED', 'SOURCE_OVERWRITE_FORBIDDEN', 'SPAN_INVALID', 'SPAN_NOT_FOUND', 'SPAN_OVERLAP', 'UNRESOLVED_STRUCTURAL_BLOCKERS', 'VAULT_INVALID', 'WORKSPACE_NOT_EMPTY', 'XLSX_STYLE_INVALID', 'XML_DTD_FORBIDDEN'])

def emit(value):print(json.dumps(value,ensure_ascii=False,indent=2))

def password(new=False):
    # No env var, argument or stdin password: keep secrets out of Agent transcripts and process lists.
    if not sys.stdin.isatty() or not sys.stderr.isatty():raise ValueError('LOCAL_TTY_REQUIRED')
    p=getpass.getpass('本地保险库口令（至少12字符，不会显示）: ')
    if len(p)<12:raise ValueError('PASSPHRASE_MIN_12')
    if new and getpass.getpass('再次输入口令: ')!=p:raise ValueError('PASSPHRASE_MISMATCH')
    return p

def doctor():
    import importlib.util,shutil,subprocess,importlib.metadata as m
    libs={x:bool(importlib.util.find_spec(x)) for x in ['lxml','cryptography','PIL','pypdf','spacy','zh_core_web_sm']}
    programs={x:bool(shutil.which(x)) for x in ['tesseract','pdftoppm']}
    langs=[]
    if programs['tesseract']:
        langs=subprocess.run(['tesseract','--list-langs'],capture_output=True,text=True).stdout.splitlines()[1:]
    ok=all(libs.values()) and all(programs.values()) and {'chi_sim','eng'}.issubset(langs)
    return {'version':__version__,'status':'READY' if ok else 'DEPENDENCIES_MISSING','libraries':libs,'programs':programs,'ocr_chinese': 'chi_sim' in langs,'ocr_english':'eng' in langs}

def main():
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
