"""All identities and secrets below are synthetic test data, never production credentials."""
from pathlib import Path
import io,zipfile
from lxml import etree as E
from PIL import Image,ImageDraw,ImageFont
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl import Workbook
from openpyxl.comments import Comment
from pptx import Presentation
from pptx.util import Inches,Pt

PERSON='赵测试';PHONE='13812345678';EMAIL='fixture.person@example.test';ID='110101199001010010';ACCOUNT='6222021234567890123';SECRET='蓝鲸测试项目';ORG='合成示例科技有限公司'
TEXT=f'原告：{PERSON}，被告：{ORG}。\n电话：{PHONE}；邮箱：{EMAIL}。\n身份证：{ID}；账号：{ACCOUNT}。\n住址：北京市朝阳区合成路99号。\n项目代号：{SECRET}。\n合同编号：HT-2026-001；案号：（2026）京0105民初123号。\n合同价款为120000元，2026年10月23日履行。北京市朝阳区人民法院受理。\n张某唯一持有73.27%股权的创始人。'
DICT={'terms':[{'text':PERSON,'kind':'PERSON','entity':'client1'},{'text':ORG,'kind':'ORG','entity':'company1'},{'text':SECRET,'kind':'SECRET','entity':'project1'}]}

def image():
    im=Image.new('RGB',(1600,650),'white');d=ImageDraw.Draw(im)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',50)
    d.text((65,80),'Synthetic legal exhibit',font=font,fill='black')
    d.text((65,220),f'Phone: {PHONE}',font=font,fill='black')
    d.text((65,360),f'Email: {EMAIL}',font=font,fill='black')
    d.text((65,500),'Amount: 120000 CNY',font=font,fill='black')
    b=io.BytesIO();im.save(b,'PNG');return b.getvalue()

def docx(path,with_image=False):
    d=Document();s=d.styles['Normal'];s.font.name='PingFang SC';s.font.size=__import__('docx').shared.Pt(11);s._element.rPr.rFonts.set(qn('w:eastAsia'),'PingFang SC')
    d.add_heading('合成法律文书 · 测试材料',0)
    p=d.add_paragraph('原告：');p.add_run(PERSON[:1]).bold=True;p.add_run(PERSON[1:])
    for line in TEXT.splitlines()[1:]:d.add_paragraph(line)
    d.sections[0].header.paragraphs[0].text='保密电话：'+PHONE
    d.sections[0].footer.paragraphs[0].text='项目：'+SECRET
    table=d.add_table(rows=2,cols=2);table.style='Table Grid';table.cell(0,0).text='主体';table.cell(0,1).text='金额';table.cell(1,0).text=PERSON;table.cell(1,1).text='120000元'
    p=d.add_paragraph();r=p.add_run('隐藏联系人：'+PERSON);r.font.hidden=True
    p=d.add_paragraph();deleted=OxmlElement('w:del');deleted.set(qn('w:id'),'10');deleted.set(qn('w:author'),PERSON);rr=OxmlElement('w:r');tt=OxmlElement('w:delText');tt.text='旧电话：'+PHONE;rr.append(tt);deleted.append(rr);p._p.append(deleted)
    p=d.add_paragraph('批注锚点');d.add_comment(p.runs,text='联系 '+PERSON+' '+PHONE,author=PERSON,initials='ZT')
    if with_image:d.add_picture(io.BytesIO(image()),width=__import__('docx').shared.Inches(5.4))
    d.core_properties.author=PERSON;d.core_properties.title=SECRET;d.save(path)
    # Footnote parts and a textbox exercise XML that python-docx doesn't expose.
    with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
    W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    root=E.fromstring(parts['word/document.xml']);body=root.find('{'+W+'}body')
    p=E.Element('{'+W+'}p');sect=body.find('{'+W+'}sectPr')
    body.insert(list(body).index(sect) if sect is not None else len(body),p)
    r=E.SubElement(p,'{'+W+'}r');ref=E.SubElement(r,'{'+W+'}footnoteReference');ref.set('{'+W+'}id','1')
    parts['word/document.xml']=E.tostring(root)
    parts['word/footnotes.xml']=f'<w:footnotes xmlns:w="{W}"><w:footnote w:id="1"><w:p><w:r><w:t>脚注 {PERSON} {PHONE}</w:t></w:r></w:p></w:footnote></w:footnotes>'.encode()
    rel=E.fromstring(parts['word/_rels/document.xml.rels']);E.SubElement(rel,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',Id='rIdFoot',Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes',Target='footnotes.xml');parts['word/_rels/document.xml.rels']=E.tostring(rel)
    ct=E.fromstring(parts['[Content_Types].xml']);E.SubElement(ct,'{http://schemas.openxmlformats.org/package/2006/content-types}Override',PartName='/word/footnotes.xml',ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml');parts['[Content_Types].xml']=E.tostring(ct)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)

def xlsx(path,with_image=False):
    w=Workbook();s=w.active;s.title='合同清单';s.append(['主体','联系方式','金额','计算']);s.append([PERSON,PHONE,120000,'=C2*2']);s['B2'].comment=Comment(EMAIL,PERSON);s['A3']=ORG;s['B3'].hyperlink='https://example.test/?person='+PERSON
    hidden=w.create_sheet('内部');hidden.sheet_state='hidden';hidden['A1']='项目代号：'+SECRET;hidden['A2']='账号：'+ACCOUNT
    if with_image:
        from openpyxl.drawing.image import Image as XLImage
        picture=XLImage(io.BytesIO(image()));picture.width=720;picture.height=292;s.add_image(picture,'A5')
    s.page_setup.orientation='landscape';s.page_setup.paperSize=s.PAPERSIZE_A4
    s.sheet_properties.pageSetUpPr.fitToPage=True;s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=1;s.print_area='A1:L24'
    w.properties.creator=PERSON;w.save(path)

def pptx(path,with_image=False):
    p=Presentation();p.slide_width=Inches(10);p.slide_height=Inches(7.5)
    slide=p.slides.add_slide(p.slide_layouts[6]);box=slide.shapes.add_textbox(Inches(.5),Inches(.3),Inches(9),Inches(4.5))
    box.text=TEXT
    for para in box.text_frame.paragraphs:
        for run in para.runs:run.font.name='PingFang SC';run.font.size=Pt(17)
    slide.notes_slide.notes_text_frame.text='讲者备注 '+PERSON+' '+PHONE
    second=p.slides.add_slide(p.slide_layouts[6]);second._element.set('show','0');second.shapes.add_textbox(Inches(1),Inches(1),Inches(8),Inches(2)).text='隐藏页：'+SECRET
    if with_image:slide.shapes.add_picture(io.BytesIO(image()),Inches(.5),Inches(5),width=Inches(7))
    p.core_properties.author=PERSON;p.save(path)

def make_all(root,with_image=True):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    (root/'sample.txt').write_text(TEXT);(root/'sample.md').write_text('# 合成材料\n'+TEXT)
    docx(root/'sample.docx',with_image);xlsx(root/'sample.xlsx',with_image);pptx(root/'sample.pptx',with_image)
    png=image();(root/'sample.png').write_bytes(png)
    im=Image.open(io.BytesIO(png));im.save(root/'sample.jpg','JPEG');im.save(root/'scan.pdf','PDF',resolution=150)
    return sorted(root.iterdir())
