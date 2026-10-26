"""Interactive user-only workflow. Run outside Agent-owned terminal sessions."""
import getpass,json,secrets,subprocess,sys
from pathlib import Path
from .workflow import scan,redact,verify
from .review import serve
from .vault import open_vault
from .platforms import open_folder

def wizard():
    if not sys.stdin.isatty() or not sys.stderr.isatty():raise ValueError('LOCAL_TTY_REQUIRED')
    print('信息隐身衣｜本地处理，不自动上传\n请选择要处理的文件；原件不会覆盖。')
    paths=choose_files()
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
        selected=choose_files(dictionary=True)
        if not selected:raise ValueError('DICTIONARY_SELECTION_CANCELLED')
        dictionary=json.loads(Path(selected[0]).read_text('utf-8'))
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
    open_folder(folder)
    return {'status':result['status'],'task_workspace':str(folder)}


def choose_files(dictionary=False):
    if sys.platform=='darwin':
        script='set fs to choose file with multiple selections allowed\nset s to ""\nrepeat with f in fs\nset s to s & POSIX path of f & linefeed\nend repeat\nreturn s'
        r=subprocess.run(['osascript','-e',script],capture_output=True,text=True)
        if r.returncode:raise ValueError('FILE_SELECTION_CANCELLED')
        return [x for x in r.stdout.splitlines() if x]
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk();root.withdraw()
        try:return list(filedialog.askopenfilenames(title='选择本地案件词典' if dictionary else '选择法律文件'))
        finally:root.destroy()
    except (ImportError,RuntimeError):raise ValueError('LOCAL_CHOOSER_UNAVAILABLE') from None
