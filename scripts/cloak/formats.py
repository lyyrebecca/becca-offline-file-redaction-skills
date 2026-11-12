from __future__ import annotations
import csv, io, re, tempfile, zipfile
import copy,math
from functools import lru_cache
from pathlib import Path, PurePosixPath
from dataclasses import dataclass,field
from lxml import etree as ET
from PIL import Image, ImageDraw,ImageOps
from pypdf import PdfReader
from .core import Hit,apply_spans
from .platform_support import resolve_tool, run_tool

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
SUPPORTED={'.docx','.xlsx','.pptx','.pdf','.png','.jpg','.jpeg','.txt','.md','.csv','.tsv','.eml','.json','.xml','.log'}
MAX_FILE=100*1024*1024;MAX_EXPANDED=300*1024*1024
PARSER=ET.XMLParser(resolve_entities=False,no_network=True,remove_blank_text=False,huge_tree=False)

@dataclass
class Unit:
    key:str
    text:str
    kind:str='text'
    nodes:list=field(default_factory=list)
    attribute:str=''
    boxes:list=field(default_factory=list)
    image:str=''
    hits:list=field(default_factory=list)
    source_ref:str=''
    preview_cells:list=field(default_factory=list)
    field:str=''


def run(cmd):
    if not cmd:raise ValueError('LOCAL_TOOL_UNAVAILABLE')
    # run_tool hides the console window that Windows would otherwise flash for each call.
    return run_tool(cmd)


def ocr(data):
    return copy.deepcopy(_ocr(data))

@lru_cache(maxsize=8)
def _ocr(data):
    # Run with a private temp directory; stdout is parsed internally, never forwarded to an Agent.
    tesseract=resolve_tool('tesseract')
    if not tesseract:raise ValueError('LOCAL_TOOL_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='lpc-ocr-') as td:
        p=Path(td)/'image.png';p.write_bytes(data)
        raw=run([tesseract,str(p),'stdout','-l','chi_sim+eng','--psm','11','tsv']).decode('utf-8')
    groups={}
    for row in csv.DictReader(io.StringIO(raw),delimiter='\t',quoting=csv.QUOTE_NONE):
        if row.get('level')!='5' or not row.get('text','').strip():continue
        key=tuple(row.get(x) for x in ['page_num','block_num','par_num','line_num'])
        groups.setdefault(key,[]).append(row)
    units=[]
    for i,rows in enumerate(groups.values()):
        text='';boxes=[]
        for row in rows:
            token=row['text'].strip()
            # Chinese OCR often separates every character. Concatenate CJK/digit tokens;
            # keep word gaps for Latin prose, while preserving exact coordinate ranges.
            if text and text[-1].isascii() and text[-1].isalpha() and token[0].isascii() and token[0].isalpha():text+=' '
            start=len(text);text+=token
            x,y,w,h=(int(row[v]) for v in ['left','top','width','height'])
            boxes.append((start,len(text),x,y,x+w,y+h,float(row['conf'])))
        units.append(Unit(str(i),text,'ocr',boxes=boxes))
    return units


def change_nodes(unit,new):
    if unit.attribute:
        unit.nodes[0].set(unit.attribute,new);return
    # Preserve surrounding runs/styles. A replacement spanning runs is inserted in its first run;
    # unaffected suffixes remain in their original run.
    old=''.join(n.text or '' for n in unit.nodes)
    if old==new:return
    import difflib
    ranges=[];p=0
    for n in unit.nodes:ranges.append((p,p+len(n.text or ''),n));p=ranges[-1][1]
    result=['' for _ in ranges]
    def index(pos):
        for i,(s,e,n) in enumerate(ranges):
            if s<=pos<e:return i
        return max(0,len(ranges)-1)
    for tag,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
        if tag=='equal':
            for i,(s,e,n) in enumerate(ranges):
                left=max(a,s);right=min(b,e)
                if left<right:result[i]+=old[left:right]
        elif tag in ('replace','insert'):result[index(a)]+=new[c:d]
    for (s,e,n),value in zip(ranges,result):n.text=value

class Document:
    def __init__(self,data,suffix):
        if len(data)>MAX_FILE:raise ValueError('FILE_TOO_LARGE')
        self.data=data;self.suffix=suffix.lower();self.text_bom=data.startswith(b'\xef\xbb\xbf');self.units=[];self.issues=[];self.images={};self.roots={};self.parts={};self.pages=[];self.manual_rectangles=[]
        if self.suffix not in SUPPORTED:raise ValueError('FORMAT_UNSUPPORTED')
        if self.suffix=='.eml':
            from email import policy
            from email.header import decode_header,make_header
            from email.parser import BytesParser
            try:message=BytesParser(policy=policy.default).parsebytes(data)
            except Exception:raise ValueError('EML_INVALID') from None
            if message.is_multipart() or message.get_content_type()!='text/plain' or message.get_filename() or message.get_content_disposition()=='attachment':raise ValueError('EML_COMPLEX_MIME_BLOCKED')
            if message.defects:raise ValueError('EML_INVALID')
            try:body=message.get_content()
            except Exception:raise ValueError('EML_CHARSET_UNSUPPORTED') from None
            if not isinstance(body,str) or '\x00' in body:raise ValueError('EML_INVALID')
            address_headers=('From','To','Cc','Bcc','Reply-To','Sender')
            text_headers=('Subject','Date','Message-ID','In-Reply-To','References')
            raw_headers={}
            for name,value in message.raw_items():raw_headers.setdefault(name.lower(),[]).append(value)
            for name in address_headers+text_headers:
                candidates=[]
                for original_name in (name,'X-LPC-'+name):
                    parsed=message.get_all(original_name,[]);raw_values=raw_headers.get(original_name.lower(),[])
                    if len(parsed)!=len(raw_values):raise ValueError('EML_INVALID_HEADER')
                    for value,raw_value in zip(parsed,raw_values):
                        generated_token=bool(re.search(r'\[P:[a-f0-9]{12}:[A-Z_]+:\d{3,}\]',raw_value))
                        try:value_text=str(make_header(decode_header(raw_value))) if original_name.lower().startswith('x-lpc-') else str(value)
                        except Exception:raise ValueError('EML_INVALID_HEADER') from None
                        if getattr(value,'defects',()) and not generated_token:raise ValueError('EML_INVALID_HEADER')
                        if any(ord(ch)<32 and ch not in '\t ' for ch in value_text):raise ValueError('EML_INVALID_HEADER')
                        candidates.append(value_text)
                for index,value_text in enumerate(candidates):self.units.append(Unit(f'header-{name}-{index}',value_text,'text',field=name))
            self.units.append(Unit('body',body,'text',field='body'))
            allowed={x.lower() for x in address_headers+text_headers+('MIME-Version','Content-Type','Content-Transfer-Encoding')}
            allowed|={('x-lpc-'+x.lower()) for x in address_headers+text_headers}
            if any(name.lower() not in allowed for name,_ in message.raw_items()):self.issues.append('EML_HEADERS_NORMALIZED')
        elif self.suffix in ('.txt','.md','.csv','.tsv','.json','.xml','.log'):
            try:text=data.decode('utf-8-sig')
            except UnicodeDecodeError:
                # GBK/ANSI files are common on Windows; refuse instead of guessing an encoding.
                raise ValueError('TEXT_ENCODING_UNSUPPORTED') from None
            if self.suffix in ('.csv','.tsv'):
                try:list(csv.reader(io.StringIO(text,newline=''),delimiter='\t' if self.suffix=='.tsv' else ','))
                except csv.Error:raise ValueError('CSV_INVALID') from None
            if self.suffix=='.json':
                import json
                try:json.loads(text)
                except (ValueError,UnicodeError):raise ValueError('JSON_INVALID') from None
            elif self.suffix=='.xml':
                try:root=ET.fromstring(data,PARSER)
                except ET.XMLSyntaxError:raise ValueError('XML_INVALID') from None
                if root.getroottree().docinfo.doctype:raise ValueError('XML_DTD_FORBIDDEN')
            self.units=[Unit('text',text)]
        elif self.suffix in ('.docx','.xlsx','.pptx'):self.office()
        elif self.suffix=='.pdf':self.pdf()
        else:self.add_image('image',data)
        for i,u in enumerate(self.units):
            u.source_ref=u.image or u.key
            if u.field:
                u.source_ref='邮件正文' if u.field=='body' else f'邮件头：{u.field}'
            if u.nodes:
                node=u.nodes[0];anc=[node]+list(node.iterancestors())
                cell=next((a for a in anc if a.tag=='{'+S+'}c'),None)
                if cell is not None:u.source_ref+='!'+cell.get('r','')
                if any(isinstance(a.tag,str) and ET.QName(a).localname in ('del','ins') for a in anc):u.source_ref+=' [修订片段，非确认现行文本]'
                if any(a.find('.//{'+W+'}vanish') is not None for a in anc[:3]):u.source_ref+=' [可能含隐藏文字]'
            u.key=f'u{i:06d}'

    def add_image(self,name,data):
        with Image.open(io.BytesIO(data)) as im:
            if im.width*im.height>35_000_000:raise ValueError('IMAGE_TOO_LARGE')
            if getattr(im,'n_frames',1)>1:self.issues.append('MULTIFRAME_IMAGE')
            im=ImageOps.exif_transpose(im).convert('RGB');buf=io.BytesIO();im.save(buf,'PNG');clean=buf.getvalue()
        self.images[name]=clean
        for unit in ocr(clean):unit.image=name;self.units.append(unit)
        # OCR is fallible: images always require explicit local visual review, even with no hits.
        self.issues.append('IMAGE_VISUAL_REVIEW')

    def pdf(self):
        reader=PdfReader(io.BytesIO(self.data))
        if reader.is_encrypted:raise ValueError('PDF_ENCRYPTED')
        if len(reader.pages)>60:raise ValueError('PDF_PAGE_LIMIT')
        # Render annotations too. Rebuilt output contains pixels only, no original PDF objects.
        pdftoppm=resolve_tool('pdftoppm')
        if not pdftoppm:raise ValueError('LOCAL_TOOL_UNAVAILABLE')
        with tempfile.TemporaryDirectory(prefix='lpc-pdf-') as td:
            p=Path(td)/'source.pdf';p.write_bytes(self.data)
            run([pdftoppm,'-r','180','-png',str(p),str(Path(td)/'page')])
            pages=sorted(Path(td).glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
            if len(pages)!=len(reader.pages):raise ValueError('PDF_RENDER_INCOMPLETE')
            for i,p in enumerate(pages):
                name=f'page{i:04d}';self.pages.append(name);self.add_image(name,p.read_bytes())

    def office(self):
        with zipfile.ZipFile(io.BytesIO(self.data)) as z:
            infos=z.infolist()
            if len(infos)>10000 or sum(x.file_size for x in infos)>MAX_EXPANDED:raise ValueError('PACKAGE_LIMIT')
            if len({x.filename for x in infos})!=len(infos):raise ValueError('PACKAGE_DUPLICATE')
            for x in infos:
                if x.flag_bits&1 or x.filename.startswith('/') or '..' in PurePosixPath(x.filename).parts:raise ValueError('PACKAGE_INVALID')
                self.parts[x.filename]=z.read(x)
        if '[Content_Types].xml' not in self.parts:raise ValueError('PACKAGE_INVALID')
        expected={'.docx':'word/document.xml','.xlsx':'xl/workbook.xml','.pptx':'ppt/presentation.xml'}
        if expected[self.suffix] not in self.parts:raise ValueError('PACKAGE_TYPE_MISMATCH')
        removed=set()
        for name,data in list(self.parts.items()):
            if 'printersettings/' in name.lower():removed.add(name)
            if name.lower().startswith('customxml/') and name.endswith('.xml'):
                root=ET.fromstring(data,PARSER)
                if ET.QName(root).namespace=='http://schemas.openxmlformats.org/officeDocument/2006/bibliography' and ET.QName(root).localname=='Sources' and len(root)==0:
                    removed.add(name)
                    removed.add(str(PurePosixPath(name).parent/('_rels/'+PurePosixPath(name).name+'.rels')))
                    # Default python-docx bibliography has an empty metadata companion.
                    companion=name.replace('item1.xml','itemProps1.xml')
                    if companion in self.parts:removed.add(companion)
        for name in removed:self.parts.pop(name,None)
        for name,data in self.parts.items():
            low=name.lower()
            self.units.append(Unit(name,name,'reference'))
            if any(x in low for x in ['embeddings/','activex/','vbaproject','customxml/','charts/','externallinks/','connections.xml','querytables/','pivotcache','pivotTables/'.lower(),'_xmlsignatures/','persons/','people.xml','richdata/']):
                self.issues.append('UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART')
            if low.startswith('docprops/thumbnail.'):
                if not low.endswith(('.png','.jpg','.jpeg')):
                    self.issues.append('UNSUPPORTED_BINARY_PART');continue
                # Strip preview content while retaining the valid image part and relationships.
                im=Image.new('RGB',(1,1),'white');b=io.BytesIO();im.save(b,'JPEG' if low.endswith(('.jpeg','.jpg')) else 'PNG');self.parts[name]=b.getvalue();continue
            if low.endswith(('.png','.jpg','.jpeg')):
                self.add_image(name,data);continue
            if not low.endswith(('.xml','.rels','.vml')):
                if not low.endswith(('.png','.jpg','.jpeg')):self.issues.append('UNSUPPORTED_BINARY_PART')
                continue
            root=ET.fromstring(data,PARSER)
            if root.getroottree().docinfo.doctype:raise ValueError('XML_DTD_FORBIDDEN')
            import posixpath
            removed_ids=set()
            for rel in list(root):
                if ET.QName(rel).localname=='Relationship':
                    base=posixpath.dirname(posixpath.dirname(name)) if '/_rels/' in name else ''
                    target=posixpath.normpath(posixpath.join(base,rel.get('Target','').lstrip('/'))) if not rel.get('Target','').startswith('/') else rel.get('Target','')[1:]
                    if target in removed:removed_ids.add(rel.get('Id'));root.remove(rel)
                elif ET.QName(rel).localname=='Override' and rel.get('PartName','').lstrip('/') in removed:root.remove(rel)
            # Printer settings relationship IDs are local to a sheet/presentation. Remove only
            # pageSetup printer references; page dimensions, margins and orientation remain.
            for e in root.iter():
                if isinstance(e.tag,str) and ET.QName(e).localname=='pageSetup':
                    for attr in list(e.attrib):
                        if ET.QName(attr).localname=='id' and ET.QName(attr).namespace=='http://schemas.openxmlformats.org/officeDocument/2006/relationships':del e.attrib[attr]
            self.roots[name]=root
            for value in sorted(set(v for e in root.iter() if isinstance(e.tag,str) for v in e.nsmap.values() if v)):
                self.units.append(Unit(name,value,'reference'))
            if low.startswith('docprops/'):
                for e in root.xpath('//comment()|//processing-instruction()'):
                    if e.getparent() is not None:e.getparent().remove(e)
                for e in root.iter():
                    if e.text:e.text=''
                    # Drop arbitrary custom metadata attributes, while retaining typed value declarations.
                    for attr in list(e.attrib):
                        if ET.QName(attr).localname in ('name','author','lastModifiedBy'):e.set(attr,'')
                continue
            used=set()
            groups=root.xpath('//*[local-name()="p" and (namespace-uri()=$w or namespace-uri()=$a)] | //s:si | //s:is',w=W,a=A,namespaces={'s':S})
            for g in groups:
                # Nearest grouping ancestor avoids duplicate processing of nested text boxes.
                nodes=[]
                for n in g.iter():
                    if not isinstance(n.tag,str):continue
                    q=ET.QName(n)
                    if q.localname not in ('t','delText','instrText') or not n.text:continue
                    ancestors=[x for x in n.iterancestors() if x in groups]
                    if ancestors and ancestors[0] is g:nodes.append(n)
                if nodes:
                    self.units.append(Unit(name, ''.join(n.text or '' for n in nodes),nodes=nodes));used.update(nodes)
            for e in root.iter():
                if not isinstance(e.tag,str):continue
                tag=ET.QName(e).localname
                if tag in ('binData','oleObject','control','altChunk','attachedTemplate'):self.issues.append('UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART')
                if tag=='instrText' and e.text:
                    code=e.text.strip().split()[0].upper() if e.text.strip() else ''
                    if code not in ('PAGE','NUMPAGES','SECTIONPAGES','TOC','REF','PAGEREF'):self.issues.append('DYNAMIC_FIELD_REVIEW')
                if tag=='fldSimple':self.issues.append('DYNAMIC_FIELD_REVIEW')
                if e not in used and e.text and e.text.strip():
                    kind='formula' if tag=='f' and ET.QName(e).namespace==S else 'text'
                    if not any(x in low for x in ('/document.xml','/header','/footer','/footnote','/endnote','/comment','/slide','/notes','/worksheet','/sharedstrings','/workbook.xml')):kind='structural'
                    self.units.append(Unit(name,e.text,kind,nodes=[e]));used.add(e)
                # Include all attribute values, including author, alternate text, sheet names,
                # hidden content, relationship targets, named ranges and bookmark names.
                for attr,value in list(e.attrib.items()):
                    if not value:continue
                    al=ET.QName(attr).localname
                    if tag=='Relationship' and al=='Target' and e.get('TargetMode')=='External':
                        if e.get('Type','').endswith('/hyperlink'):e.set(attr,'about:blank')
                        else:self.issues.append('EXTERNAL_DEPENDENCY')
                        continue
                    if tag=='Relationship' and al in ('Id','Type','TargetMode'):continue
                    if value.startswith(('http://schemas.','http://purl.','urn:schemas-')):continue
                    reference = al in ('id','Id','styleId','ref') or (tag=='Relationship' and al=='Target') or (tag in ('sheet','definedName','bookmarkStart') and al=='name')
                    self.units.append(Unit(name,value,'reference' if reference else 'attribute',nodes=[e],attribute=attr))
            # tails, XML comments and processing instructions are not rendered text: discard them.
            for e in root.iter():
                if not isinstance(e.tag,str):continue
                if e.tail and e.tail.strip():self.issues.append('UNSUPPORTED_XML_TAIL')
            for e in root.xpath('//comment()|//processing-instruction()'):
                if e.getparent() is not None:e.getparent().remove(e)
        if self.suffix=='.xlsx':self.prepare_xlsx_preview()
        self.issues=sorted(set(self.issues))

    def prepare_xlsx_preview(self):
        """Attach stable sheet/cell locations for a local review grid; never expose raw sheet names as trusted markup."""
        import posixpath
        workbook=self.roots.get('xl/workbook.xml');rels=self.roots.get('xl/_rels/workbook.xml.rels')
        if workbook is None or rels is None:return
        relmap={e.get('Id'):e.get('Target','') for e in rels if ET.QName(e).localname=='Relationship'}
        relns='http://schemas.openxmlformats.org/officeDocument/2006/relationships';sheets={}
        for index,sheet in enumerate(workbook.iter('{'+S+'}sheet')):
            target=relmap.get(sheet.get('{'+relns+'}id'),'')
            if not target:continue
            path=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl',target))
            sheets[path]={'sheet':index+1,'hidden':sheet.get('state') in ('hidden','veryHidden')}
        shared_root=self.roots.get('xl/sharedStrings.xml');shared=list(shared_root) if shared_root is not None else []
        refs={}
        for path,info in sheets.items():
            root=self.roots.get(path)
            if root is None:continue
            for cell in root.iter('{'+S+'}c'):
                if cell.get('t')!='s':continue
                value=cell.find('{'+S+'}v')
                if value is None or not value.text:continue
                try:index=int(value.text)
                except ValueError:continue
                row=cell.getparent();hidden=info['hidden'] or bool(row is not None and row.get('hidden') in ('1','true'))
                refs.setdefault(index,[]).append({'sheet':info['sheet'],'cell':cell.get('r',''),'hidden':hidden})
        for unit in self.units:
            if unit.key=='xl/sharedStrings.xml' and shared:
                si=next((a for node in unit.nodes for a in node.iterancestors() if a.tag=='{'+S+'}si'),None)
                if si is not None:unit.preview_cells=refs.get(shared.index(si),[])
            elif unit.key in sheets:
                cell_node=next((a for node in unit.nodes for a in [node]+list(node.iterancestors()) if a.tag=='{'+S+'}c'),None)
                cell=cell_node.get('r','') if cell_node is not None else ''
                if re.fullmatch(r'[A-Z]{1,3}[1-9]\d*',cell):
                    row=cell_node.getparent();hidden=sheets[unit.key]['hidden'] or bool(row is not None and row.get('hidden') in ('1','true'))
                    unit.preview_cells=[{'sheet':sheets[unit.key]['sheet'],'cell':cell,'hidden':hidden}]

    def image_masks(self):
        """Return numbered mask rectangles for local preview labels and delete/jump actions."""
        positions=[];number=0
        for name,data in self.images.items():
            im=Image.open(io.BytesIO(data));width,height=im.size
            for u in self.units:
                if u.image!=name:continue
                for hi,hit in enumerate(u.hits):
                    if not hit.mask:continue
                    for a,b,x,y,r,bot,conf in u.boxes:
                        if hit.start<b and hit.end>a:
                            pad=max(4,min(80,math.ceil((r-x)/max(1,b-a)*1.4)))
                            number+=1;positions.append({'position':number,'image':name,'box':[max(0,x-pad),max(0,y-4),min(width,r+pad),min(height,bot+4)],'kind':'hit','unit_key':u.key,'hit_index':hi})
            for ri,rect in enumerate(self.manual_rectangles):
                if rect['image']==name:
                    number+=1;positions.append({'position':number,'image':name,'box':list(rect['box']),'kind':'manual','manual_index':ri})
        return positions

    def render_images(self,replacer):
        output={}
        masks=self.image_masks()
        for name,data in self.images.items():
            im=Image.open(io.BytesIO(data)).convert('RGB');draw=ImageDraw.Draw(im)
            for position in masks:
                if position['image']==name:draw.rectangle(tuple(position['box']),fill='black')
            b=io.BytesIO();im.save(b,'JPEG' if name.lower().endswith(('.jpg','.jpeg')) else 'PNG');output[name]=b.getvalue()
        return output

    def output(self,replacer):
        if self.suffix=='.eml':
            from email.message import EmailMessage
            from email import policy
            message=EmailMessage(policy=policy.SMTP)
            body=''
            for u in self.units:
                value=apply_spans(u.text,u.hits,lambda h:replacer(u,h))
                if u.field=='body':body=value
                elif u.field:message['X-LPC-'+u.field]=value
            message.set_content(body,subtype='plain',charset='utf-8')
            return message.as_bytes()
        if self.suffix in ('.txt','.md','.csv','.tsv','.eml','.json','.xml','.log'):
            raw=apply_spans(self.units[0].text,self.units[0].hits,lambda h:replacer(self.units[0],h)).encode('utf-8')
            if self.suffix in ('.csv','.tsv') and self.text_bom:raw=b'\xef\xbb\xbf'+raw
            if self.suffix=='.json':
                import json
                try:json.loads(raw)
                except ValueError:raise ValueError('JSON_OUTPUT_INVALID') from None
            elif self.suffix=='.xml':
                try:root=ET.fromstring(raw,PARSER)
                except ET.XMLSyntaxError:raise ValueError('XML_OUTPUT_INVALID') from None
                if root.getroottree().docinfo.doctype:raise ValueError('XML_DTD_FORBIDDEN')
            return raw
        images=self.render_images(replacer)
        if self.suffix=='.pdf':
            pages=[Image.open(io.BytesIO(images[n])).convert('RGB') for n in self.pages]
            b=io.BytesIO();pages[0].save(b,'PDF',save_all=True,append_images=pages[1:],resolution=180.0);return b.getvalue()
        if self.suffix in ('.png','.jpg','.jpeg'):
            im=Image.open(io.BytesIO(images['image'])).convert('RGB');b=io.BytesIO();im.save(b,'PNG' if self.suffix=='.png' else 'JPEG');return b.getvalue()
        changed=[]
        for u in self.units:
            if u.kind=='ocr':continue
            new=apply_spans(u.text,u.hits,lambda h:replacer(u,h))
            if new!=u.text:
                if u.kind in ('formula','reference'):raise ValueError('SENSITIVE_FORMULA_OR_REFERENCE_BLOCKED')
                change_nodes(u,new);changed.append(u)
        if self.suffix=='.xlsx':self.wrap_excel(changed)
        parts=dict(self.parts);parts.update(images)
        for name,root in self.roots.items():parts[name]=ET.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in parts.items():z.writestr(name,data)
        return b.getvalue()

    def wrap_excel(self,changed):
        """Keep columns and formulas; wrap only modified cells to avoid clipped tokens."""
        styles=self.roots.get('xl/styles.xml')
        if styles is None:return
        xfs=styles.find('{'+S+'}cellXfs')
        if xfs is None:return
        touched=set();shared=set()
        shared_root=self.roots.get('xl/sharedStrings.xml')
        sis=list(shared_root) if shared_root is not None else []
        for unit in changed:
            for node in unit.nodes:
                for a in [node]+list(node.iterancestors()):
                    if a.tag=='{'+S+'}c':touched.add(a)
                    if a.tag=='{'+S+'}si' and a in sis:shared.add(sis.index(a))
        cache={}
        for name,root in self.roots.items():
            if not name.startswith('xl/worksheets/') or not name.endswith('.xml'):continue
            for cell in root.iter('{'+S+'}c'):
                vv=cell.find('{'+S+'}v')
                if cell.get('t')=='s' and vv is not None and vv.text and int(vv.text) in shared:touched.add(cell)
                if cell not in touched:continue
                if cell.get('t') in (None,'n') and vv is not None and vv.text and ('[P:' in vv.text or re.fullmatch(r'\*{3,}',vv.text)):
                    if cell.find('{'+S+'}f') is not None:raise ValueError('SENSITIVE_FORMULA_BLOCKED')
                    value=vv.text;cell.remove(vv);cell.set('t','inlineStr')
                    inline=ET.SubElement(cell,'{'+S+'}is');ET.SubElement(inline,'{'+S+'}t').text=value
                idx=int(cell.get('s','0'))
                if idx>=len(xfs):raise ValueError('XLSX_STYLE_INVALID')
                if idx not in cache:
                    xf=copy.deepcopy(xfs[idx]);alignment=xf.find('{'+S+'}alignment')
                    if alignment is None:alignment=ET.SubElement(xf,'{'+S+'}alignment')
                    alignment.set('wrapText','1');xf.set('applyAlignment','1');cache[idx]=len(xfs);xfs.append(xf)
                cell.set('s',str(cache[idx]))
                if cell.get('t')=='s' and vv is not None:text=''.join(sis[int(vv.text)].itertext())
                else:text=''.join(cell.itertext())
                letters=re.sub('[0-9]','',cell.get('r','A1'));colnum=0
                for char in letters:colnum=colnum*26+ord(char)-64
                sheet_format=root.find('{'+S+'}sheetFormatPr')
                width=float(sheet_format.get('defaultColWidth',sheet_format.get('baseColWidth','8.43'))) if sheet_format is not None else 8.43
                for col in root.iter('{'+S+'}col'):
                    if int(col.get('min','0'))<=colnum<=int(col.get('max','0')):width=float(col.get('width','13'))
                chars=sum(2 if ord(c)>255 else 1 for c in text)
                height=min(409.0,max(20.0,math.ceil(chars/max(1,width-1))*15.0+6))
                row=cell.getparent()
                if row is not None and row.tag=='{'+S+'}row':row.set('ht',str(max(float(row.get('ht','15')),height)));row.set('customHeight','1')
        xfs.set('count',str(len(xfs)))
