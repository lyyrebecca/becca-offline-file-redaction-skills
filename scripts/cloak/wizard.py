"""Interactive user-only workflow. Run outside Agent-owned terminal sessions."""
import getpass,json,secrets,subprocess,sys
from pathlib import Path
from .workflow import scan,redact,verify
from .review import serve
from .vault import open_vault

def wizard():
    if not sys.stdin.isatty():raise ValueError('LOCAL_TTY_REQUIRED')
    if sys.platform!='darwin':raise ValueError('MACOS_CHOOSER_REQUIRED')
    print('信息隐身衣｜本地处理，不自动上传\n请选择要处理的文件；原件不会覆盖。')
    script='''set fs to choose file with prompt "选择法律文件（可多选）" with multiple selections allowed
set s to ""
repeat with f in fs
set s to s & POSIX path of f & linefeed
end repeat
return s'''
    r=subprocess.run(['osascript','-e',script],capture_output=True,text=True)
    if r.returncode:raise ValueError('FILE_SELECTION_CANCELLED')
    paths=[x for x in r.stdout.splitlines() if x]
    if not paths:raise ValueError('NO_INPUT')
    choice=input('用途：1 交给AI分析（默认） / 2 外部审阅 / 3 公开分享：').strip()
    policy={'':'ai','1':'ai','2':'external','3':'public'}.get(choice)
    if policy is None:raise ValueError('POLICY_INVALID')
    pw=getpass.getpass('设置本地保险库口令（至少12字符）: ')
    if len(pw)<12:raise ValueError('PASSPHRASE_MIN_12')
    if getpass.getpass('再次输入口令: ')!=pw:raise ValueError('PASSPHRASE_MISMATCH')
    folder=Path.home()/'Documents/信息隐身衣'/('task-'+secrets.token_hex(6))
    dictionary=None
    if input('是否使用本机案件词典？输入 y 使用，其余跳过：').strip().lower()=='y':
        r=subprocess.run(['osascript','-e','POSIX path of (choose file with prompt "选择本地JSON案件词典")'],capture_output=True,text=True)
        if r.returncode:raise ValueError('DICTIONARY_SELECTION_CANCELLED')
        dictionary=json.loads(Path(r.stdout.strip()).read_text('utf-8'))
    print('正在本地扫描；原文不会出现在终端输出中。',flush=True)
    scan(paths,folder,pw,policy,dictionary)
    print('请在自动打开的本机浏览器中逐区复核并确认。',flush=True)
    serve(folder,pw)
    if not open_vault(folder/'private/task.lpcv',pw).get('reviewed'):raise ValueError('LOCAL_REVIEW_REQUIRED')
    result=redact(folder,pw)
    if result['status']=='CHECKED':result=verify(folder,pw)
    print('处理状态：'+result['status'])
    print('任务目录：'+str(folder))
    print('仅 share 文件夹是候选交付件；private保险库留在本机。不会自动上传。')
    subprocess.run(['open',str(folder)])
    return {'status':result['status'],'task_workspace':str(folder)}
