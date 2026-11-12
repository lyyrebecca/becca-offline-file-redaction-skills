"""Interactive user-only workflow. Run outside Agent-owned terminal sessions.

File selection uses the native Tk dialog on every platform (Windows, macOS, Linux),
with a typed-path fallback when Tk is missing, so no OS-specific AppleScript is needed.
"""
import getpass, json, secrets, sys
from pathlib import Path
from .workflow import scan, redact, verify
from .review import serve
from .vault import open_vault
from .platform_support import open_folder, path_length_warning, task_home


def _dialog(kind: str, title: str) -> list[str]:
    """kind is 'files' or 'file'; returns an empty list when Tk is unavailable or cancelled."""
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        return []
    root = None
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.update()
        # macOS shows dialogs behind the terminal otherwise.
        root.lift()
        try:
            root.focus_force()
        except tkinter.TclError:
            pass
        if kind == 'files':
            selected = filedialog.askopenfilenames(parent=root, title=title)
        else:
            selected = filedialog.askopenfilename(parent=root, title=title)
    except Exception:
        return []
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    return [str(item) for item in (selected or ()) if str(item).strip()]


def choose_files() -> list[str]:
    paths = _dialog('files', '选择法律文件（可多选）')
    if paths:
        return paths
    print('未选择文件，或本机缺少图形对话框。可粘贴完整文件路径，多个路径用英文分号分隔：')
    typed = input('文件路径：').strip()
    return [x.strip().strip('"') for x in typed.replace('；', ';').split(';') if x.strip()]


def wizard():
    if not sys.stdin.isatty():
        raise ValueError('LOCAL_TTY_REQUIRED')
    print('信息隐身衣｜本地处理，不自动上传\n请选择要处理的文件；原件不会覆盖。')
    paths = choose_files()
    if not paths:
        raise ValueError('FILE_SELECTION_CANCELLED')
    choice = input('用途：1 交给AI分析（默认） / 2 外部审阅 / 3 公开分享：').strip()
    policy = {'': 'ai', '1': 'ai', '2': 'external', '3': 'public'}.get(choice)
    if policy is None:
        raise ValueError('POLICY_INVALID')
    pw = getpass.getpass('设置本地保险库口令（至少12字符，不会显示）: ')
    if len(pw) < 12:
        raise ValueError('PASSPHRASE_MIN_12')
    if getpass.getpass('再次输入口令: ') != pw:
        raise ValueError('PASSPHRASE_MISMATCH')
    folder = task_home().parent / '信息隐身衣' / ('task-' + secrets.token_hex(6))
    warning = path_length_warning(folder)
    if warning:
        print(warning, flush=True)
    dictionary = None
    if input('是否使用本机案件词典？输入 y 使用，其余跳过：').strip().lower() == 'y':
        selected = _dialog('file', '选择本地 JSON 案件词典')
        if not selected:
            typed = input('词典 JSON 完整路径：').strip().strip('"')
            selected = [typed] if typed else []
        if not selected:
            raise ValueError('DICTIONARY_SELECTION_CANCELLED')
        dictionary = json.loads(Path(selected[0]).read_text('utf-8'))
    print('正在本地扫描；原文不会出现在终端输出中。', flush=True)
    scan(paths, folder, pw, policy, dictionary)
    print('请在自动打开的本机浏览器中逐区复核并确认。', flush=True)
    serve(folder, pw)
    if not open_vault(folder / 'private/task.lpcv', pw).get('reviewed'):
        raise ValueError('LOCAL_REVIEW_REQUIRED')
    result = redact(folder, pw)
    if result['status'] == 'CHECKED':
        result = verify(folder, pw)
    print('处理状态：' + result['status'])
    print('任务目录：' + str(folder))
    print('仅 share 文件夹是候选交付件；private 保险库留在本机。不会自动上传。')
    open_folder(folder)
    return {'status': result['status'], 'task_workspace': str(folder)}
