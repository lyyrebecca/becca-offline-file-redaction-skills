"""Authenticated local desktop workbench. Original values never leave loopback or logs."""
from __future__ import annotations
import json,secrets,threading,urllib.parse,webbrowser,subprocess,tempfile,os,shutil,io
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from .localhttp import LocalThreadingHTTPServer as ThreadingHTTPServer
from PIL import Image
from . import workflow as w
from .formats import Document,ocr,_ocr
from .vault import seal,open_vault,atomic
from .organize import set_assignments,CATEGORIES
from .scenarios import ROLES,PURPOSES,RECIPIENTS,ROLE_HINTS,scenario_from
from .core import LABELS,local_model
from .platforms import data_home,lock_file,open_folder

def exported(job):return bool(job) and any('output_name' in f for f in job.get('files',[]))

ASSETS=Path(__file__).resolve().parents[2]/'assets'

def serve(port=0,open_browser=True,ready=None,home=None,singleton_file=None):
    os.umask(0o077)
    root=Path(home or Path.home()/'Documents'/'信息隐身衣任务').resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=tempfile.TemporaryDirectory(prefix='lpc-desktop-');tmp=Path(temporary.name)
    state={'status':'IDLE','stage':'准备就绪','done':0,'total':0,'uploads':[],'workspace':None,'job':None,'password':None,'seen':[],'result':None,'error':None}
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
        w.scan(paths,ws,pw,dictionary=dictionary,scenario=config,progress=progress)
        job=open_vault(ws/'private'/'task.lpcv',pw)
        for f,u in zip(job['files'],state['uploads']):f['local_label']=u['label']
        with lock:state.update(workspace=str(ws),job=job,password=pw,status='REVIEW',stage='识别完成，请确认归属与内容',done=len(paths),seen=[])
        save()
        for row in state['uploads']:Path(row['path']).unlink(missing_ok=True)
        state['uploads']=[]
    def doc(fi):
        if fi not in documents:
            if len(documents)>=2:documents.pop(next(iter(documents)))
            f=state['job']['files'][fi];documents[fi]=Document(w.input_data(f),f['suffix'])
        d=documents[fi];w._attach(d,state['job']['files'][fi]);d.manual_rectangles=state['job']['files'][fi].get('rectangles',[])
        return d
    def public_state():
        result={k:state[k] for k in ('status','stage','done','total','workspace','result','error')}
        result.update(roles=ROLES,purposes=PURPOSES,recipients=RECIPIENTS,role_hints=ROLE_HINTS,categories=CATEGORIES,labels=LABELS,csrf=csrf)
        result['uploads']=[{'name':r['label'],'size':r['size']} for r in state['uploads']]
        if state['job']:
            j=state['job'];result['task']=w.stats(j);result['scenario']=j.get('scenario',{});result['groups_confirmed']=j.get('groups_confirmed',False)
            result['files']=[{'index':i,'name':f.get('local_label',Path(f['source']).name),'suffix':f['suffix'],'case_id':f.get('case_id','PENDING'),'category':f.get('category','other'),'reason':f.get('group_reason',''),'duplicate_of':f.get('duplicate_of'),'issues':f['issues'],'seen':i in state['seen'],'teaching':f.get('teaching',{})} for i,f in enumerate(j['files'])]
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
                    self.send({'units':[{'index':i,**u} for i,u in enumerate(f['units'])],'images':[{'index':i,'width':Image.open(io.BytesIO(raw)).width,'height':Image.open(io.BytesIO(raw)).height} for i,raw in enumerate(d.images.values())],'rectangles':f.get('rectangles',[]),'issues':f['issues']})
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
                    if exported(state.get('job')) and path in ('/groups','/decision','/manual','/rectangle','/remove-rectangle','/seen','/export'):raise ValueError('TASK_EXPORT_FROZEN')
                    if path=='/paths':
                        if state['status']!='IDLE':raise ValueError('JOB_STATE_INVALID')
                        from .formats import SUPPORTED
                        paths=[]
                        for value in data['paths']:
                            p=Path(value).expanduser().resolve(strict=True)
                            if p.is_dir():paths.extend(x for x in sorted(p.rglob('*')) if x.is_file() and not x.is_symlink() and not any(n.startswith('.') for n in x.relative_to(p).parts))
                            else:paths.append(p)
                        if not paths:raise ValueError('NO_INPUT')
                        if any(p.suffix.lower() not in SUPPORTED for p in paths):raise ValueError('FORMAT_UNSUPPORTED')
                        if len(paths)+len(state['uploads'])>100 or sum(p.stat().st_size for p in paths)+sum(x['size'] for x in state['uploads'])>250*1024*1024 or any(p.stat().st_size>100*1024*1024 for p in paths):raise ValueError('BATCH_LIMIT')
                        for p in paths:
                            target=tmp/(secrets.token_hex(6)+p.suffix.lower());atomic(target,p.read_bytes());state['uploads'].append({'path':str(target),'label':p.name,'size':p.stat().st_size})
                    elif path=='/scan':
                        if not state['uploads']:raise ValueError('NO_INPUT')
                        pw=data['password']
                        if not isinstance(pw,str) or len(pw)<12:raise ValueError('PASSPHRASE_MIN_12')
                        if pw!=data['password_again']:raise ValueError('PASSPHRASE_MISMATCH')
                        config=scenario_from(data.get('scenario')).dict();dictionary=data.get('dictionary',{})
                        state.update(status='BUSY',stage='正在准备本地处理',error=None,total=len(state['uploads']))
                        background(lambda:scan(config,dictionary,pw))
                    elif path=='/groups':
                        set_assignments(state['job'],data['assignments']);state['seen']=[];save()
                    elif path=='/decision':
                        fi=int(data['fi']);u=state['job']['files'][fi]['units'][int(data['ui'])];h=u['hits'][int(data['hi'])]
                        if not data['mask'] and not data.get('reason','').strip():raise ValueError('KEEP_REQUIRES_REASON')
                        h['mask']=bool(data['mask']);h['reason']=str(data.get('reason',''))[:300];h['entity']=str(data.get('entity',h.get('entity','')))[:80];state['seen']=[i for i in state['seen'] if i!=fi];state['job']['reviewed']=False;save()
                    elif path=='/manual':
                        fi=int(data['fi']);ui=int(data['ui']);u=state['job']['files'][fi]['units'][ui]
                        import re
                        value=data['value'];matches=list(re.finditer(re.escape(value),u['text'])) if value else []
                        if not matches:raise ValueError('SPAN_NOT_FOUND')
                        # Prevalidate entire request before changing state.
                        if any(m.start()<h['end'] and m.end()>h['start'] for m in matches for h in u['hits']):raise ValueError('SPAN_OVERLAP')
                        for m in matches:w.add_manual(state['job'],fi,ui,*m.span(),data['kind'])
                        state['seen']=[i for i in state['seen'] if i!=fi];save()
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
                        fi=int(data['fi']);f=state['job']['files'][fi];folder=Path(state['workspace'])/'restored';folder.mkdir(exist_ok=True,mode=0o700)
                        target=folder/('restored-'+secrets.token_hex(4)+f['suffix'])
                        edited=data.get('edited') or None
                        result=w.restore(state['workspace'],state['password'],target,edited,fi)
                        self.send({'ok':True,'result':result,'output':str(target) if target.exists() else None});return
                    elif path=='/reset':
                        for row in state['uploads']:Path(row['path']).unlink(missing_ok=True)
                        documents.clear();_ocr.cache_clear();state.update(status='IDLE',stage='准备就绪',uploads=[],workspace=None,job=None,password=None,seen=[],result=None,error=None)
                    elif path=='/close':
                        self.send({'ok':True});threading.Thread(target=server.shutdown,daemon=True).start();return
                    else:raise ValueError('REQUEST_INVALID')
                self.send({'ok':True})
            except Exception as e:
                safe={'GROUP_REVIEW_REQUIRED':'请确认文件归属；待确认归属不能直接通过。','ALL_FILES_MUST_BE_REVIEWED':'请逐个检查文件并确认。','UNRESOLVED_STRUCTURAL_BLOCKERS':'文档存在不支持的内容，不能跳过检查。','LOCAL_REVIEW_INCOMPLETE':'请完成全部复核确认。','KEEP_REQUIRES_REASON':'保留敏感内容时必须填写理由。','PASSPHRASE_MIN_12':'口令至少需要12个字符。','PASSPHRASE_MISMATCH':'两次口令不一致。','SPAN_OVERLAP':'补充内容与已有命中重叠，请先检查现有项。','FORMAT_UNSUPPORTED':'此文件格式尚不支持；未进行处理。','BATCH_LIMIT':'本批最多100个文件、合计250MB。','OUTPUT_ALREADY_EXISTS':'已有导出结果；请新建任务，避免覆盖。','TASK_EXPORT_FROZEN':'已导出的任务不能再修改复核；请新建任务处理新的副本。','GROUP_ASSIGNMENT_INVALID':'请为每份文件指定有效案件编号与材料性质。','FOLDER_OPEN_FAILED':'未能打开文件管理器；请复制完整文件夹路径手动前往。','BUSY':'正在处理，请等待。'}
                message=safe.get(str(e),'操作未完成，请检查输入、口令、文件状态或依赖。') if isinstance(e,ValueError) else '操作未完成，未返回任何原文错误信息。'
                self.send({'error':message},400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    url=f'http://127.0.0.1:{server.server_port}/?key={secret}'
    if singleton_file:atomic(Path(singleton_file),json.dumps({'port':server.server_port,'activate':activate}).encode())
    if ready:ready(url,server)
    if open_browser:webbrowser.open(url)
    try:server.serve_forever()
    finally:
        if singleton_file:
            try:
                file=Path(singleton_file)
                if json.loads(file.read_text('utf-8')).get('activate')==activate:file.unlink()
            except (OSError,ValueError):pass
        server.server_close();state['password']=None;state['job']=None;documents.clear();_ocr.cache_clear();local_model.cache_clear();temporary.cleanup()


def reactivate(path):
    """Local launcher-to-server control, distinct from the one-use browser bootstrap."""
    import http.client
    try:
        record=json.loads(Path(path).read_text('utf-8'));port=record['port']
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
    folder=data_home();folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    descriptor=folder/'desktop-session.json'
    with (folder/'desktop-launch.lock').open('a+b') as handle:
        os.chmod(handle.name,0o600);lock_file(handle)
        url=reactivate(descriptor)
        if url:
            lock_file(handle,unlock=True);webbrowser.open(url);return
        def ready(url,server):lock_file(handle,unlock=True)
        serve(ready=ready,singleton_file=descriptor)
