"""Ephemeral loopback-only review. Never route this page, its pixels or source to a cloud Agent."""
from __future__ import annotations
import base64, copy, html, io, secrets, threading, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler
from .localhttp import LocalHTTPServer as HTTPServer
from pathlib import Path
from PIL import Image
from .vault import open_vault,seal,unb64
from .workflow import review_update,add_manual,publish,stats,SOFT_ISSUES,_attach,input_data
from .formats import Document
from .core import LABELS,Hit
ISSUE_LABELS={'IMAGE_VISUAL_REVIEW':'全部图片、扫描页及遮挡预览（包括签名、人脸、二维码）','CROSS_FILE_IDENTITY_REVIEW':'跨文件身份关系，未自动合并同名主体','ENTITY_AMBIGUITY_REVIEW':'同名主体、别称、间接身份线索与需要保留的法律细节'}
BLOCK_LABELS={'UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART':'含暂不支持的嵌入对象、动态数据、自定义内容或签名。请先制作不带这些内容的静态工作副本。','UNSUPPORTED_BINARY_PART':'含暂不支持的二进制或图片格式，不能跳过检查。','DYNAMIC_FIELD_REVIEW':'含可刷新内容的动态域，请先在本机制作静态副本。','EXTERNAL_DEPENDENCY':'文档依赖外部文件或数据源，请先在本机消除外部依赖。','SENSITIVE_FORMULA_BLOCKED':'公式或公式缓存中含敏感内容，需要人工处理，不能直接替换。','SENSITIVE_REFERENCE_BLOCKED':'工作表名、引用名、包路径或命名空间中含敏感内容，直接改名可能破坏文档。','SENSITIVE_NUMERIC_WITH_FORMULAS':'数字身份标识所在的工作簿含公式，需要先确认计算依赖。','UNSUPPORTED_XML_TAIL':'含尚不能完整检查的XML内容。','MULTIFRAME_IMAGE':'图片包含多帧，本版不能只处理第一帧。'}

def serve(workspace,password,port=0,open_browser=True,ready=None):
    ws=Path(workspace).resolve();vp=ws/'private'/'task.lpcv';job=open_vault(vp,password)
    if job['status']!='NEEDS_REVIEW' or job.get('mapping'):raise ValueError('REVIEW_STATE_INVALID')
    secret=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);cookie=secrets.token_urlsafe(32)
    bootstrapped=False
    docs=[Document(input_data(f),f['suffix']) for f in job['files']]
    job.setdefault('seen',[])
    locations=[(fi,ui) for fi,f in enumerate(job['files']) for ui,u in enumerate(f['units']) if u['hits'] or u['kind'] in ('text','ocr','formula')]
    def save():seal(vp,job,password);publish(ws/'scan-report.json',stats(job))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def send_page(self,body,status=200,auth=False):
            data=body.encode('utf-8');self.send_response(status)
            self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            if auth:self.send_header('Set-Cookie',f'lpc={cookie}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers();self.wfile.write(data)
        def authorized(self):
            host=self.headers.get('Host','')
            return host==f'127.0.0.1:{server.server_port}' and f'lpc={cookie}' in self.headers.get('Cookie','').split('; ')
        def wrap(self,body):return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>信息隐身衣 · 本地复核</title><style>body{font:16px -apple-system,sans-serif;max-width:1100px;margin:35px auto;padding:0 24px;color:#20343a;background:#f3f5f4}h1,h2{color:#145b54}section{background:white;border-radius:12px;padding:22px;margin:18px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;background:#eef4f2;padding:18px}input,select,button{font:inherit;margin:5px;padding:8px}button{background:#145b54;color:white;border:0;border-radius:6px}img{max-width:100%;border:1px solid #ccc}small{color:#53646c}.error{color:#942d36}table{width:100%;text-align:left}td{padding:8px;border-bottom:1px solid #ddd}</style><h1>信息隐身衣 · 本地复核</h1><p>此页面含原文，仅供本机查看。不要上传截图、复制源代码到 AI，或通过远程浏览器代理查看。</p>'''+body+'</html>'
        def token(self):return f'<input type="hidden" name="csrf" value="{csrf}">'
        def do_GET(self):
            nonlocal bootstrapped
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if not self.authorized():
                if not bootstrapped and q.get('key')==[secret] and self.headers.get('Host')==f'127.0.0.1:{server.server_port}':
                    bootstrapped=True
                    self.send_response(303);self.send_header('Location','/');self.send_header('Set-Cookie',f'lpc={cookie}; HttpOnly; SameSite=Strict; Path=/');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cache-Control','no-store');self.end_headers();return
                self.send_page('Forbidden',403);return
            try:pos=int(q.get('unit',['0'])[0]);pos=max(0,min(pos,max(0,len(locations)-1)))
            except ValueError:pos=0
            body=f'<p>任务 {job["task"]} · 策略 {html.escape(job["policy"])} · 已检查 {len(job["seen"])}/{len(locations)} 个文本区域</p>'
            if locations:
                fi,ui=locations[pos];f=job['files'][fi];u=f['units'][ui]
                body+=f'<section><h2>文件 {fi+1} / 文本区域 {ui+1}</h2><small>{html.escape(Path(f["source"]).name)}</small><pre>{html.escape(u["text"])}</pre>'
                body+=f'<form action="/decision" method="post">{self.token()}<input type="hidden" name="pos" value="{pos}"><table><tr><th>脱敏</th><th>类别 / 原文</th><th>保留理由</th></tr>'
                for hi,h in enumerate(u['hits']):
                    checked='checked' if h['mask'] else ''
                    body+=f'<tr><td><input type="checkbox" name="mask{hi}" {checked}></td><td>{html.escape(LABELS.get(h["kind"],h["kind"]))}：{html.escape(u["text"][h["start"]:h["end"]])}<br><small>{html.escape(h["rule"])}</small></td><td><input name="reason{hi}" value="{html.escape(h.get("reason",""),quote=True)}" placeholder="保留必须说明理由"></td></tr>'
                body+='</table><button>保存本区域并看下一个</button></form>'
                body+=f'<form action="/manual" method="post">{self.token()}<input type="hidden" name="pos" value="{pos}"><h3>补充漏检</h3><input name="value" required placeholder="本区域内需要隐藏的完整原文"><select name="kind">'+''.join(f'<option value="{k}">{v}</option>' for k,v in LABELS.items())+'</select><button>标记本区域全部同文命中</button></form>'
                body+=f'<p><a href="/?unit={max(0,pos-1)}">上一个</a>　<a href="/?unit={min(len(locations)-1,pos+1)}">下一个</a>（跳转不计为已检查）</p></section>'
            for fi,doc in enumerate(docs):
                for ii,(name,img) in enumerate(doc.images.items()):
                    im=Image.open(io.BytesIO(img))
                    body+=f'<section><h2>文件 {fi+1} 图片 {ii+1}：{im.width} × {im.height}</h2><img src="data:image/png;base64,{base64.b64encode(img).decode()}"><p>检查 OCR 漏检区域；需要时按原图像素坐标添加黑块。已添加 {sum(r["image"]==name for r in job["files"][fi].get("rectangles",[]))} 个区域。</p>'
                    _attach(doc,job['files'][fi])
                    doc.manual_rectangles=job['files'][fi].get('rectangles',[])
                    preview=doc.render_images(None)[name]
                    body+=f'<h3>脱敏预览</h3><img src="data:image/png;base64,{base64.b64encode(preview).decode()}">'
                    body+=f'<form action="/rectangle" method="post">{self.token()}<input type="hidden" name="fi" value="{fi}"><input type="hidden" name="ii" value="{ii}">'
                    for field in ['x','y','right','bottom']:body+=f'<input type="number" name="{field}" placeholder="{field}" required style="width:110px">'
                    body+='<button>添加黑块</button></form></section>'
            issues=sorted(set(i for f in job['files'] for i in f['issues']))
            body+='<section><h2>完成复核</h2><p>所有文本区域均需检查并保存；结构性阻断不能通过勾选消除。</p>'
            for issue in issues:
                if issue not in SOFT_ISSUES:body+=f'<p class="error">暂不能完成：{html.escape(BLOCK_LABELS.get(issue,"存在尚未解决的文档检查问题。"))}<br><small>{html.escape(issue)}</small></p>'
            body+=f'<form action="/approve" method="post">{self.token()}'
            for issue in issues:
                if issue in SOFT_ISSUES:body+=f'<p><label><input type="checkbox" name="confirm" value="{issue}" required>我已检查：{html.escape(ISSUE_LABELS.get(issue,issue))}</label></p>'
            body+='<button>确认复核并关闭本地会话</button></form></section>'
            self.send_page(self.wrap(body))
        def do_POST(self):
            if not self.authorized():self.send_page('Forbidden-session',403);return
            origin=self.headers.get('Origin')
            isolated_same_origin=(origin=='null' and self.headers.get('Sec-Fetch-Site')=='same-origin')
            if origin and origin!=f'http://127.0.0.1:{server.server_port}' and not isolated_same_origin:self.send_page('Forbidden-origin',403);return
            snapshot=copy.deepcopy(job)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<65536:raise ValueError('REQUEST_INVALID')
                q=urllib.parse.parse_qs(self.rfile.read(length).decode('utf-8'),keep_blank_values=True)
                if q.get('csrf')!=[csrf]:self.send_page('Forbidden',403);return
                pos=int(q.get('pos',['0'])[0]);pos=max(0,min(pos,max(0,len(locations)-1)))
                if self.path in ('/decision','/manual'):
                    fi,ui=locations[pos];u=job['files'][fi]['units'][ui]
                    if self.path=='/manual':
                        val=q['value'][0]
                        if not val:raise ValueError('SPAN_INVALID')
                        import re
                        matches=list(re.finditer(re.escape(val),u['text']))
                        if not matches:raise ValueError('SPAN_NOT_FOUND')
                        for m in matches:add_manual(job,fi,ui,*m.span(),q['kind'][0])
                        key=f'{fi}:{ui}'
                        if key in job['seen']:job['seen'].remove(key)
                    else:
                        for hi,h in enumerate(u['hits']):
                            h['mask']=f'mask{hi}' in q;h['reason']=q.get(f'reason{hi}',[''])[0][:300]
                            if not h['mask'] and not h['reason'].strip():raise ValueError('KEEP_REQUIRES_REASON')
                        key=f'{fi}:{ui}'
                        if key not in job['seen']:job['seen'].append(key)
                        pos=min(len(locations)-1,pos+1)
                elif self.path=='/rectangle':
                    fi=int(q['fi'][0]);ii=int(q['ii'][0]);name=list(docs[fi].images)[ii]
                    im=Image.open(io.BytesIO(docs[fi].images[name]));box=[int(q[k][0]) for k in ('x','y','right','bottom')]
                    if not 0<=box[0]<box[2]<=im.width or not 0<=box[1]<box[3]<=im.height:raise ValueError('RECTANGLE_INVALID')
                    job['files'][fi].setdefault('rectangles',[]).append({'image':name,'box':box})
                elif self.path=='/approve':
                    if set(job['seen'])!=set(f'{fi}:{ui}' for fi,ui in locations):raise ValueError('ALL_REGIONS_MUST_BE_REVIEWED')
                    review_update(job,confirmations=q.get('confirm',[]));save()
                    self.send_page(self.wrap('<section><h2>本地复核已保存</h2><p>可以返回终端执行脱敏。此页面不会自动上传任何内容。</p></section>'))
                    threading.Thread(target=server.shutdown,daemon=True).start();return
                else:raise ValueError('REQUEST_INVALID')
                job['reviewed']=False;save()
                self.send_response(303);self.send_header('Location',f'/?unit={pos}');self.send_header('Cache-Control','no-store');self.end_headers()
            except (ValueError,KeyError,IndexError):
                job.clear();job.update(snapshot)
                self.send_page(self.wrap('<section class="error">未保存：请检查保留理由、区域范围、复核完整性或结构性阻断。<p><a href="/">返回</a></p></section>'),400)
    server=HTTPServer(('127.0.0.1',port),Handler)
    server.timeout=1
    url=f'http://127.0.0.1:{server.server_port}/?key={secret}'
    if ready:ready(url,server)
    if open_browser:webbrowser.open(url)
    try:server.serve_forever()
    finally:server.server_close()
