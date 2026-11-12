"""Authenticated local desktop workbench. Original values never leave loopback or logs."""
from __future__ import annotations
import json,secrets,threading,urllib.parse,webbrowser,tempfile,os,io,sys
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from PIL import Image
from . import workflow as w
from .formats import Document,ocr,_ocr
from .vault import seal,open_vault,atomic
from .scenarios import ROLES,PURPOSES,RECIPIENTS,ROLE_HINTS,scenario_from
from .core import LABELS,local_model
from .platform_support import FileLock,open_folder,remove_quietly,secure_dir,task_home

def exported(job):return bool(job) and any('output_name' in f for f in job.get('files',[]))

ASSETS=Path(__file__).resolve().parents[2]/'assets'

def open_local_browser(url):
    """Open the loopback URL; print it when no default browser is registered."""
    try:
        opened=webbrowser.open(url)
    except Exception:
        opened=False
    if not opened:
        print('未能自动打开浏览器，请手动复制以下本机地址到浏览器：',flush=True)
        print(url,flush=True)
    return opened

def serve(port=0,open_browser=True,ready=None,home=None,singleton_file=None):
    os.umask(0o077)
    root=Path(home or task_home()).resolve();secure_dir(root)
    temporary=tempfile.TemporaryDirectory(prefix='lpc-desktop-');tmp=Path(temporary.name)
    state={'status':'IDLE','stage':'准备就绪','done':0,'total':0,'uploads':[],'workspace':None,'job':None,'password':None,'seen':[],'result':None,'error':None,'learning':{'status':'not_found','count':0}}
    activate=secrets.token_urlsafe(32);secret=secrets.token_urlsafe(32);cookie=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);boot=False;lock=threading.RLock();documents={}
    def save():
        seal(Path(state['workspace'])/'private'/'task.lpcv',state['job'],state['password'])
    def progress(done,total,stage):
        with lock:state.update(done=done,total=total,stage='本机识别中；首次加载中文模型可能稍慢')
    def background(action):
        def run():
            try:action()
            except Exception as e:
                # Do not put exception values or tracebacks into either UI or stdout.
                with lock:state.update(status='ERROR',error='处理未完成，请核对文件、口令、复核项目与依赖；原件未覆盖。',stage='需要处理',error_type=type(e).__name__)
        threading.Thread(target=run,daemon=True).start()
    def scan(config,dictionary,pw):
        ws=root/('任务-'+secrets.token_hex(6));paths=[r['path'] for r in state['uploads']]
        library=root/'.learning-rules.lpcv';learning={'status':'not_found','count':0}
        if library.exists():
            try:
                saved=open_vault(library,pw);terms=list(dictionary.get('terms',[]));known={(x.get('text'),x.get('kind')) for x in terms if isinstance(x,dict)}
                for item in saved.get('terms',[]):
                    if (item.get('text'),item.get('kind')) not in known:terms.append(item);known.add((item.get('text'),item.get('kind')))
                dictionary={**dictionary,'terms':terms};learning={'status':'loaded','count':len(saved.get('terms',[]))}
            except Exception:learning={'status':'locked','count':0}
        w.scan(paths,ws,pw,dictionary=dictionary,scenario=config,progress=progress)
        job=open_vault(ws/'private'/'task.lpcv',pw)
        for f,u in zip(job['files'],state['uploads']):f['local_label']=u['label']
        with lock:state.update(workspace=str(ws),job=job,password=pw,status='REVIEW',stage='识别完成，请逐份查看本机预览',done=len(paths),seen=[],learning=learning)
        save()
        for row in state['uploads']:remove_quietly(row['path'])
        state['uploads']=[]
    def doc(fi):
        if fi not in documents:
            if len(documents)>=2:documents.pop(next(iter(documents)))
            f=state['job']['files'][fi];documents[fi]=Document(w.input_data(f),f['suffix'])
        d=documents[fi];w._attach(d,state['job']['files'][fi]);d.manual_rectangles=state['job']['files'][fi].get('rectangles',[])
        return d
    def public_state():
        result={k:state[k] for k in ('status','stage','done','total','workspace','result','error')}
        result.update(roles=ROLES,purposes=PURPOSES,recipients=RECIPIENTS,role_hints=ROLE_HINTS,labels=LABELS,csrf=csrf,learning=state.get('learning'))
        result['uploads']=[{'index':i,'name':r['label'],'size':r['size']} for i,r in enumerate(state['uploads'])]
        result['blockers']=[]
        if state['job']:
            j=state['job'];result['task']=w.stats(j);result['scenario']=j.get('scenario',{})
            result['files']=[{'index':i,'name':f.get('local_label',Path(f['source']).name),'suffix':f['suffix'],'case_id':f.get('case_id','CASE001'),'duplicate_of':f.get('duplicate_of'),'issues':f['issues'],'seen':i in state['seen'],'teaching':f.get('teaching',{})} for i,f in enumerate(j['files'])]
            result['blockers']=w.structural_blockers(j['files'])
            result['soft_confirmations']=w.required_soft_confirmations(j['files'])
        else:
            result['soft_confirmations']=[]
        return result
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def send(self,data,status=200,mime='application/json; charset=utf-8',headers=None):
            if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False).encode()
            if isinstance(data,str):data=data.encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            for k,v in {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",**(headers or {})}.items():self.send_header(k,v)
            self.end_headers();self.wfile.write(data)
        def host(self):return self.headers.get('Host')==f'127.0.0.1:{server.server_port}'
        def auth(self):return self.host() and f'lpc_{server.server_port}={cookie}' in self.headers.get('Cookie','').split('; ')
        def do_GET(self):
            nonlocal boot
            q=urllib.parse.urlsplit(self.path);args=urllib.parse.parse_qs(q.query)
            if not self.auth():
                with lock:
                    if not boot and self.host() and q.path=='/' and args.get('key')==[secret]:
                        boot=True;self.send(b'',303,headers={'Location':'/','Set-Cookie':f'lpc_{server.server_port}={cookie}; HttpOnly; SameSite=Strict; Path=/'});return
                self.send({'error':'FORBIDDEN'},403);return
            try:
                if q.path=='/state':
                    with lock:self.send(public_state())
                elif q.path=='/review':
                    fi=int(args['fi'][0]);f=state['job']['files'][fi];d=doc(fi)
                    unit_indexes={u['key']:i for i,u in enumerate(f['units'])};positions=d.image_masks();images=[]
                    for i,(name,raw) in enumerate(d.images.items()):
                        masks=[]
                        for position in positions:
                            if position['image']!=name:continue
                            item=dict(position)
                            if item['kind']=='hit':item['unit_index']=unit_indexes.get(item.pop('unit_key'),-1)
                            item['label']=f"位置 {item['position']}";masks.append(item)
                        images.append({'index':i,'name':name,'width':Image.open(io.BytesIO(raw)).width,'height':Image.open(io.BytesIO(raw)).height,'masks':masks})
                    self.send({'units':[{'index':i,**u} for i,u in enumerate(f['units'])],'images':images,'rectangles':f.get('rectangles',[]),'issues':f['issues'],'issue_details':w.issue_details(f['issues'])})
                elif q.path=='/image':
                    fi=int(args['fi'][0]);ii=int(args['ii'][0]);d=doc(fi);name=list(d.images)[ii]
                    raw=d.render_images(None)[name] if args.get('masked')==['1'] else d.images[name]
                    self.send(raw,mime='image/png')
                elif q.path in ('/','/app.css','/app.js','/brand-icon.jpg'):
                    path=ASSETS/('ui/index.html' if q.path=='/' else 'brand-icon.jpg' if q.path=='/brand-icon.jpg' else 'ui/'+q.path[1:])
                    self.send(path.read_bytes(),mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.jpg':'image/jpeg'}[path.suffix])
                else:self.send({'error':'NOT_FOUND'},404)
            except Exception:self.send({'error':'LOCAL_VIEW_FAILED'},400)
        def do_POST(self):
            nonlocal boot,secret
            if self.path=='/activate' and self.host() and not self.headers.get('Origin') and secrets.compare_digest(self.headers.get('X-LPC-Activate',''),activate):
                with lock:
                    secret=secrets.token_urlsafe(32);boot=False
                    self.send({'url':f'http://127.0.0.1:{server.server_port}/?key={secret}'})
                return
            origin=self.headers.get('Origin');expected=f'http://127.0.0.1:{server.server_port}'
            same=origin==expected or (origin=='null' and self.headers.get('Sec-Fetch-Site')=='same-origin')
            if not self.auth() or not same or self.headers.get('X-CSRF')!=csrf:self.send({'error':'FORBIDDEN'},403);return
            try:
                length=int(self.headers.get('Content-Length','0'));path=urllib.parse.urlsplit(self.path).path
                limit=100*1024*1024 if path=='/upload' else 1024*1024
                if not 0<length<=limit:raise ValueError('REQUEST_INVALID')
                raw=self.rfile.read(length)
                if path=='/upload':
                    if state['status']!='IDLE':raise ValueError('JOB_STATE_INVALID')
                    suffix=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)['suffix'][0].lower()
                    from .formats import SUPPORTED
                    if suffix not in SUPPORTED:raise ValueError('FORMAT_UNSUPPORTED')
                    if len(state['uploads'])>=100 or sum(x['size'] for x in state['uploads'])+length>250*1024*1024:raise ValueError('BATCH_LIMIT')
                    p=tmp/(secrets.token_hex(6)+suffix);atomic(p,raw)
                    label=urllib.parse.unquote(self.headers.get('X-File-Name','材料'))[:255]
                    state['uploads'].append({'path':str(p),'label':label,'size':length});self.send({'ok':True});return
                data=json.loads(raw)
                with lock:
                    if state['status']=='BUSY' and path not in ('/close',):raise ValueError('BUSY')
                    if exported(state.get('job')) and path in ('/decision','/manual','/learn','/rectangle','/remove-rectangle','/seen','/export'):raise ValueError('TASK_EXPORT_FROZEN')
                    if path=='/paths':
                        if state['status']!='IDLE':raise ValueError('JOB_STATE_INVALID')
                        from .formats import SUPPORTED
                        paths=[]
                        for value in data['paths']:
                            # Explorer's "Copy as path" adds double quotes around Windows paths.
                            p=Path(str(value).strip().strip('"')).expanduser().resolve(strict=True)
                            if p.is_dir():paths.extend(x for x in sorted(p.rglob('*')) if x.is_file() and not x.is_symlink() and not any(n.startswith('.') for n in x.relative_to(p).parts))
                            else:paths.append(p)
                        if not paths:raise ValueError('NO_INPUT')
                        if any(p.suffix.lower() not in SUPPORTED for p in paths):raise ValueError('FORMAT_UNSUPPORTED')
                        if len(paths)+len(state['uploads'])>100 or sum(p.stat().st_size for p in paths)+sum(x['size'] for x in state['uploads'])>250*1024*1024 or any(p.stat().st_size>100*1024*1024 for p in paths):raise ValueError('BATCH_LIMIT')
                        for p in paths:
                            target=tmp/(secrets.token_hex(6)+p.suffix.lower());atomic(target,p.read_bytes());state['uploads'].append({'path':str(target),'label':p.name,'size':p.stat().st_size})
                    elif path=='/remove-upload':
                        if state['status']!='IDLE':raise ValueError('JOB_STATE_INVALID')
                        index=data.get('index')
                        if type(index) is not int or not 0<=index<len(state['uploads']):raise ValueError('UPLOAD_INDEX_INVALID')
                        removed=state['uploads'].pop(index);remove_quietly(removed['path'])
                    elif path=='/scan':
                        if not state['uploads']:raise ValueError('NO_INPUT')
                        pw=data['password']
                        if not isinstance(pw,str) or len(pw)<12:raise ValueError('PASSPHRASE_MIN_12')
                        if pw!=data['password_again']:raise ValueError('PASSPHRASE_MISMATCH')
                        config=scenario_from(data.get('scenario')).dict();dictionary=data.get('dictionary',{})
                        state.update(status='BUSY',stage='正在准备本地处理',error=None,total=len(state['uploads']))
                        background(lambda:scan(config,dictionary,pw))
                    elif path=='/decision':
                        fi=int(data['fi']);u=state['job']['files'][fi]['units'][int(data['ui'])];h=u['hits'][int(data['hi'])]
                        if not data['mask'] and not data.get('reason','').strip():raise ValueError('KEEP_REQUIRES_REASON')
                        h['mask']=bool(data['mask']);h['reason']=str(data.get('reason',''))[:300];h['entity']=str(data.get('entity',h.get('entity','')))[:80];state['seen']=[i for i in state['seen'] if i!=fi];state['job']['reviewed']=False;save()
                    elif path in ('/manual','/learn'):
                        fi=int(data['fi']);ui=int(data['ui']);remember=path=='/learn' and data.get('remember') is True
                        value=str(data.get('value','')).strip();kind=data.get('kind','SECRET')
                        profile=root/'.learning-rules.lpcv';saved={'version':1,'terms':[]}
                        if remember and profile.exists():
                            try:saved=open_vault(profile,state['password'])
                            except Exception:raise ValueError('LEARNING_VAULT_LOCKED') from None
                        result=w.learn_across_task(state['job'],value,kind)
                        if remember:
                            if not any(x.get('text')==value and x.get('kind')==kind for x in saved.get('terms',[])):saved.setdefault('terms',[]).append({'text':value,'kind':kind,'entity':''})
                            from .vault import seal as seal_vault
                            seal_vault(profile,saved,state['password']);state['learning']={'status':'loaded','count':len(saved.get('terms',[]))}
                        state['seen']=[];save()
                    elif path in ('/rectangle','/remove-rectangle'):
                        fi=int(data['fi']);f=state['job']['files'][fi]
                        if path=='/remove-rectangle':f.setdefault('rectangles',[]).pop(int(data['index']))
                        else:
                            d=doc(fi);name=list(d.images)[int(data['ii'])];im=Image.open(io.BytesIO(d.images[name]));box=[int(x) for x in data['box']]
                            if len(box)!=4 or not 0<=box[0]<box[2]<=im.width or not 0<=box[1]<box[3]<=im.height:raise ValueError('RECTANGLE_INVALID')
                            f.setdefault('rectangles',[]).append({'image':name,'box':box})
                        state['seen']=[i for i in state['seen'] if i!=fi];state['job']['reviewed']=False;save()
                    elif path=='/seen':
                        fi=int(data['fi'])
                        if not 0<=fi<len(state['job']['files']) or data.get('confirmed') is not True:raise ValueError('LOCAL_REVIEW_INCOMPLETE')
                        if fi not in state['seen']:state['seen'].append(fi)
                    elif path=='/export':
                        j=state['job']
                        if set(state['seen'])!=set(range(len(j['files']))):raise ValueError('ALL_FILES_MUST_BE_REVIEWED')
                        w.review_update(j,confirmations=data.get('confirmations'));save()
                        state.update(status='BUSY',stage='正在导出并复查脱敏件',error=None)
                        def export():
                            result=w.redact(state['workspace'],state['password']);verification=w.verify(state['workspace'],state['password'])
                            state.update(job=open_vault(Path(state['workspace'])/'private'/'task.lpcv',state['password']),status='DONE',result={'status':result['status'],'verification':verification['status'],'outputs':result['outputs']},stage='导出完成' if verification['status']=='CHECKED' else '导出结果仍待复核')
                        background(export)
                    elif path=='/open':
                        target=Path(state['workspace'])/('share' if data.get('kind')=='share' else 'restored' if data.get('kind')=='restored' else '')
                        if not target.is_dir():raise ValueError('OUTPUT_NOT_FOUND')
                        open_folder(target)
                    elif path=='/unlock':
                        ws=Path(data['workspace']).expanduser().resolve();pw=data['password'];j=open_vault(ws/'private'/'task.lpcv',pw)
                        documents.clear();state.update(workspace=str(ws),password=pw,job=j,status='DONE' if exported(j) else 'REVIEW',seen=[],error=None,stage='已在本机解锁')
                    elif path=='/restore':
                        fi=int(data['fi']);f=state['job']['files'][fi];folder=Path(state['workspace'])/'restored';secure_dir(folder)
                        target=folder/('restored-'+secrets.token_hex(4)+f['suffix'])
                        edited=data.get('edited') or None
                        result=w.restore(state['workspace'],state['password'],target,edited,fi)
                        self.send({'ok':True,'result':result,'output':str(target) if target.exists() else None});return
                    elif path=='/reset':
                        for row in state['uploads']:remove_quietly(row['path'])
                        documents.clear();_ocr.cache_clear();state.update(status='IDLE',stage='准备就绪',uploads=[],workspace=None,job=None,password=None,seen=[],result=None,error=None)
                    elif path=='/close':
                        self.send({'ok':True});threading.Thread(target=server.shutdown,daemon=True).start();return
                    else:raise ValueError('REQUEST_INVALID')
                if path in ('/manual','/learn'):
                    self.send({'ok':True,'occurrences':result['occurrences'],'affected_files':result['files']});return
                self.send({'ok':True})
            except Exception as e:
                safe={'GROUP_REVIEW_REQUIRED':'请重新建立一个单案件任务；每批文件默认属于同一案件。','ALL_FILES_MUST_BE_REVIEWED':'请逐个检查文件并确认。','UNRESOLVED_STRUCTURAL_BLOCKERS':'仍有结构性阻断未解决；请返回交付页逐项查看对应材料。人工确认不能覆盖阻断。','LOCAL_REVIEW_INCOMPLETE':'请完成全部复核确认。','KEEP_REQUIRES_REASON':'保留敏感内容时必须填写理由。','PASSPHRASE_MIN_12':'口令至少需要12个字符。','PASSPHRASE_MISMATCH':'两次口令不一致。','UPLOAD_INDEX_INVALID':'导入列表已变化，请刷新后重试。','SPAN_OVERLAP':'选中文字与已有命中边界重叠；请先处理对应候选项。','LEARN_VALUE_INVALID':'请选择1至500个字符并选择有效的信息类别。','LEARNING_VAULT_LOCKED':'本机加密学习库使用了不同口令；未改动学习库。请取消“记入学习库”或使用此前口令。','FORMAT_UNSUPPORTED':'此文件格式尚不支持；未进行处理。','BATCH_LIMIT':'本批最多100个文件、合计250MB。','OUTPUT_ALREADY_EXISTS':'已有导出结果；请新建任务，避免覆盖。','TASK_EXPORT_FROZEN':'已导出的任务不能再修改复核；请新建任务处理新的副本。','FOLDER_OPEN_FAILED':'未能打开本机文件管理器；请复制完整文件夹路径手动打开。','BUSY':'正在处理，请等待。'}
                message=safe.get(str(e),'操作未完成，请检查输入、口令、文件状态或依赖。') if isinstance(e,ValueError) else '操作未完成，未返回任何原文错误信息。'
                payload={'error':message}
                if isinstance(e,ValueError) and str(e)=='UNRESOLVED_STRUCTURAL_BLOCKERS' and state.get('job'):
                    payload['blockers']=w.structural_blockers(state['job']['files'])
                self.send(payload,400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    url=f'http://127.0.0.1:{server.server_port}/?key={secret}'
    if singleton_file:atomic(Path(singleton_file),json.dumps({'port':server.server_port,'activate':activate}).encode())
    if ready:ready(url,server)
    if open_browser:open_local_browser(url)
    try:server.serve_forever()
    finally:
        if singleton_file:
            try:
                file=Path(singleton_file)
                if json.loads(file.read_text()).get('activate')==activate:file.unlink()
            except (OSError,ValueError):pass
        server.server_close();state['password']=None;state['job']=None;documents.clear();_ocr.cache_clear();local_model.cache_clear();temporary.cleanup()


def reactivate(path):
    """Local launcher-to-server control, distinct from the one-use browser bootstrap."""
    import http.client
    try:
        record=json.loads(Path(path).read_text());port=record['port']
        if type(port) is not int or not 0<port<65536:return None
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
        try:
            conn.request('POST','/activate',body=b'{}',headers={'X-LPC-Activate':record['activate']})
            response=conn.getresponse()
            if response.status!=200:return None
            url=json.loads(response.read(4096))['url'];parsed=urllib.parse.urlsplit(url)
            if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.port!=port or parsed.path!='/':return None
            return url
        finally:conn.close()
    except (OSError,ValueError,TypeError,KeyError,http.client.HTTPException):return None

def launch():
    import hashlib
    from runtime import runtime_home
    skill_root=Path(__file__).resolve().parents[2]
    instance=hashlib.sha256(str(skill_root).encode('utf-8')).hexdigest()[:16]
    folder=runtime_home()/'sessions'/instance;secure_dir(folder)
    descriptor=folder/'desktop-session.json'
    lock=FileLock(folder/'desktop-launch.lock')
    if not lock.acquire():
        # Another workbench already owns this skill folder: focus it instead of starting a
        # second server. Windows has no blocking flock, so this path must never raise.
        url=reactivate(descriptor)
        if url:
            open_local_browser(url)
            print('信息隐身衣工作台已在运行，已在浏览器中打开现有会话。')
        else:
            print('另一个信息隐身衣工作台正在启动或运行；请稍候重试，或关闭旧窗口后再打开。')
        return
    try:
        url=reactivate(descriptor)
        if url:
            open_local_browser(url)
            print('信息隐身衣工作台已在运行，已在浏览器中打开现有会话。')
            return
        serve(singleton_file=descriptor)
    finally:
        lock.release()
