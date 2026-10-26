"""Derived material is built from the reviewed sanitized units, never source filenames."""
import re,tempfile,subprocess
from pathlib import Path
from .core import apply_spans

def markdown(doc,replacer,index):
    rows=[f'# 材料 {index+1:03d}', '', '> 辅助读取副本；不代替原版式文档。修订、隐藏及 OCR 内容不视为确认事实。', '']
    for u in doc.units:
        if u.kind not in ('text','ocr','formula'):continue
        covered=any(rect['image']==u.image and any(max(x,rect['box'][0])<min(right,rect['box'][2]) and max(y,rect['box'][1])<min(bottom,rect['box'][3]) for a,b,x,y,right,bottom,conf in u.boxes) for rect in doc.manual_rectangles)
        text='[手工遮挡区域：本行 OCR 不导出]' if covered else apply_spans(u.text,u.hits,lambda h:replacer(u,h))
        if not text.strip():continue
        ref=u.source_ref or u.key
        rows += [f'## 来源 {u.key}', f'位置：`{ref.replace("`", "")}`'+(' · OCR，须对照图片' if u.kind=='ocr' else ''), '']
        fence='`'*(max([len(m.group()) for m in re.finditer(r'`+',text)]+[2])+1)
        rows += [fence+'text',text,fence,'']
    if doc.images:rows += ['> 图片的版式、签名、图表请对照同目录脱敏文件；OCR 不代表完整视觉内容。','']
    return '\n'.join(rows).encode('utf-8')

def index_files(job,pending):
    rows=['# 脱敏材料索引','','仅包含本任务的中性编号。归属由本机使用者确认。','']
    dates=['# 日期索引','','这是出现位置索引，不是事实时间线；可能包含修订或 OCR 文字。','']
    md=dict((n,d.decode('utf-8')) for n,d in pending if n.endswith('.md'))
    for i,f in enumerate(job['files']):
        name=f['output_name'];rows += [f'- 材料 {i+1:03d} · {f.get("case_id", "")} · `{name}`']
        if name+'.md' in md:
            rows += [f'  - 读取版：`{name}.md`（按来源区域编号）']
            current=''
            for line in md[name+'.md'].splitlines():
                if line.startswith('## 来源 '):current=line[6:]
                for value in re.findall(r'\d{4}(?:年|[-/])\d{1,2}(?:月|[-/])\d{1,2}日?',line):dates += [f'- {value} · 材料 {i+1:03d} · {current}']
    return {'材料与来源索引.md':('\n'.join(rows)+'\n').encode(),'日期索引.md':('\n'.join(dates)+'\n').encode()}

def ppt_pdf(data):
    from .platforms import libreoffice
    exe=libreoffice()
    if exe is None:raise ValueError('LIBREOFFICE_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='lpc-slides-') as tmp:
        root=Path(tmp);p=root/'material.pptx';p.write_bytes(data)
        command=[str(exe),'-env:UserInstallation='+ (root/'profile').as_uri(),'--headless','--convert-to','pdf','--outdir',str(root),str(p)]
        try:r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
        except (OSError,subprocess.TimeoutExpired):raise ValueError('PDF_EXPORT_FAILED') from None
        target=root/'material.pdf'
        if r.returncode or not target.exists():raise ValueError('PDF_EXPORT_FAILED')
        # Rebuild through pixels once more: no notes, attachments or original text objects.
        from .formats import Document
        return Document(target.read_bytes(),'.pdf').output(lambda u,h:'')

def verify_markdown(data,detector,kept,masked):
    # NER is run on every emitted source block independently, preserving original region
    # context. Machine-generated anchors are not names (e.g. spaCy mislabels `xml`).
    # A second full-byte text pass still checks all deterministic and known-original rules.
    from .workflow import verify_data
    from .core import Detector
    from .formats import Document,Unit
    rules=Detector(detector.policy,detector.dictionary,use_ner=False)
    rules.preserve_dates=detector.preserve_dates;rules.preserve_amounts=detector.preserve_amounts
    full=verify_data(data,'.md',rules,kept,masked)
    blocks=re.findall(r'^(`{3,})text\n(.*?)^\1$',data.decode('utf-8'),re.M|re.S)
    doc=Document(data,'.md');doc.units=[Unit(f'md{i:06d}',text.rstrip('\n')) for i,(fence,text) in enumerate(blocks)]
    semantic=verify_data(data,'.md',detector,kept,masked,doc)
    residual=full['residuals']+semantic['residuals'];blockers=full['blockers']+semantic['blockers']
    return {'status':'CHECKED' if not residual and not blockers else 'NEEDS_REVIEW','residual_count':len(residual),'residuals':residual,'blockers':blockers}
