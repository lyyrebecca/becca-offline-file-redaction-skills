from __future__ import annotations
import csv, io, re, subprocess, tempfile, zipfile
import copy,math
from functools import lru_cache
from pathlib import Path, PurePosixPath
from dataclasses import dataclass,field
from lxml import etree as ET
from PIL import Image, ImageDraw,ImageOps
from pypdf import PdfReader
from .core import Hit,apply_spans

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
SUPPORTED={'.docx','.xlsx','.pptx','.pdf','.png','.jpg','.jpeg','.txt','.md'}
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


def run(cmd):
    try:
        r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
    except (OSError,subprocess.TimeoutExpired):raise ValueError('LOCAL_TOOL_UNAVAILABLE') from None
    if r.returncode:raise ValueError('LOCAL_TOOL_FAILED')
    return r.stdout


def ocr(data):
    return copy.deepcopy(_ocr(data))

@lru_cache(maxsize=8)
def _ocr(data):
    # Run with a private temp directory; stdout is parsed internally, never forwarded to an Agent.
    with tempfile.TemporaryDirectory(prefix='lpc-ocr-') as td:
        p=Path(td)/'image.png';p.write_bytes(data)
        raw=run(['tesseract',str(p),'stdout','-l','chi_sim+eng','--psm','11','tsv']).decode('utf-8')
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
        self.data=data;self.suffix=suffix.lower();self.units=[];self.issues=[];self.images={};self.roots={};self.parts={};self.pages=[];self.manual_rectangles=[]
        if self.suffix not in SUPPORTED:raise ValueError('FORMAT_UNSUPPORTED')
        if self.suffix in ('.txt','.md'):
            self.units=[Unit('text',data.decode('utf-8-sig'))]
        elif self.suffix in ('.docx','.xlsx','.pptx'):self.office()
        elif self.suffix=='.pdf':self.pdf()
        else:self.add_image('image',data)
        for i,u in enumerate(self.units):
            u.source_ref=u.image or u.key
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
        with tempfile.TemporaryDirectory(prefix='lpc-pdf-') as td:
            p=Path(td)/'source.pdf';p.write_bytes(self.data)
            run(['pdftoppm','-r','180','-png',str(p),str(Path(td)/'page')])
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
        self.issues=sorted(set(self.issues))

    def render_images(self,replacer):
        output={}
        for name,data in self.images.items():
            im=Image.open(io.BytesIO(data)).convert('RGB');draw=ImageDraw.Draw(im)
            for u in self.units:
                if u.image!=name:continue
                for hit in u.hits:
                    if not hit.mask:continue
                    for a,b,x,y,r,bot,conf in u.boxes:
                        if hit.start<b and hit.end>a:
                            # Some OCR engines infer an edge glyph outside the reported word box.
                            # Expand horizontally by ~1.4 character widths, not just a cosmetic border.
                            pad=max(4,min(80,math.ceil((r-x)/max(1,b-a)*1.4)))
                            draw.rectangle((max(0,x-pad),max(0,y-4),min(im.width,r+pad),min(im.height,bot+4)),fill='black')
            for rect in self.manual_rectangles:
                if rect['image']==name:draw.rectangle(tuple(rect['box']),fill='black')
            b=io.BytesIO();im.save(b,'JPEG' if name.lower().endswith(('.jpg','.jpeg')) else 'PNG');output[name]=b.getvalue()
        return output

    def output(self,replacer):
        if self.suffix in ('.txt','.md'):
            return apply_spans(self.units[0].text,self.units[0].hits,lambda h:replacer(self.units[0],h)).encode('utf-8')
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
                if cell.get('t') in (None,'n') and vv is not None and vv.text and '[P:' in vv.text:
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
