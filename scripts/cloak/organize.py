"""Conservative rule-based matter grouping. Recommendations require local confirmation."""
import re,hashlib
CATEGORIES={'pleadings':'01_诉讼文书','contracts':'02_合同协议','evidence':'03_证据材料','decisions':'04_裁判程序','slides':'05_教学课件','research':'06_通用研究','other':'07_其他材料'}
CASE_RE=re.compile(r'[（(]\s*(\d{4})\s*[）)]\s*([\u4e00-\u9fffA-Za-z0-9]{1,15}?\d{1,8}号)')
CONTRACT_RE=re.compile(r'(?:合同编号|协议编号)[：:\s]*([A-Za-z0-9_\-/]{3,60})')

def nature(text,suffix):
    if suffix=='.pptx':return 'slides'
    for key,words in [('pleadings',['起诉状','答辩状','上诉状','仲裁申请书']),('decisions',['判决书','裁定书','执行通知','受理通知','开庭传票']),('contracts',['合同','协议','签约','签署']),('evidence',['聊天记录','转账','流水','收据','发票','证据','凭证']),('research',['法律法规','研究笔记','文献综述','通用模板'])]:
        if any(x in text[:6000] for x in words):return key
    return 'evidence' if suffix in ('.png','.jpg','.jpeg') else 'other'

def file_text(record):return '\n'.join(u['text'] for u in record['units'] if u['kind'] in ('text','ocr','formula'))

def propose(files,organization='auto'):
    groups={};next_id=0;seen={}
    for i,f in enumerate(files):
        text=file_text(f);f['category']=nature(text,f['suffix']);f['duplicate_of']=seen.get(f['sha256'])
        seen.setdefault(f['sha256'],i)
        keys=sorted(set('case:'+a+re.sub(r'\s+','',b) for a,b in CASE_RE.findall(text[:12000])))
        if not keys:keys=sorted(set('contract:'+x for x in CONTRACT_RE.findall(text[:6000])))
        f['group_reason']='明确案号或合同编号' if len(keys)==1 else '多标识待确认' if keys else '未找到可靠归属标识'
        if organization=='single':key='single';f['group_reason']='用户指定单一案件 / 项目'
        elif len(keys)==1:key=keys[0]
        elif f['category']=='research':key='COMMON'
        else:key='PENDING'
        if key in ('COMMON','PENDING'):case_id=key
        else:
            if key not in groups:next_id+=1;groups[key]=f'CASE{next_id:03d}'
            case_id=groups[key]
        f['case_id']=case_id
    return {'case_count':len(groups),'pending':sum(f['case_id']=='PENDING' for f in files),'duplicates':sum(f['duplicate_of'] is not None for f in files)}

def set_assignments(job,assignments):
    # Validate the whole transaction before mutating any assignment.
    if not isinstance(assignments,list) or len(assignments)!=len(job['files']):raise ValueError('GROUP_ASSIGNMENT_INVALID')
    seen=set()
    for row in assignments:
        i=row['index'];case=row['case_id']
        if type(i) is not int or not 0<=i<len(job['files']) or i in seen:raise ValueError('GROUP_ASSIGNMENT_INVALID')
        seen.add(i);category=row.get('category',job['files'][i].get('category','other'))
        if not isinstance(case,str) or not re.fullmatch(r'CASE\d{3}|COMMON|PENDING',case) or category not in CATEGORIES:raise ValueError('GROUP_ASSIGNMENT_INVALID')
    for row in assignments:
        f=job['files'][row['index']];f['case_id']=row['case_id'];f['category']=row.get('category',f.get('category','other'))
    job['groups_confirmed']=True;job['reviewed']=False;job['status']='NEEDS_REVIEW'

def relative_name(record,index):
    case=record.get('case_id','PENDING')
    folder='通用资料' if case=='COMMON' else '待确认归属' if case=='PENDING' else '案件'+case[4:]
    return folder+'/'+CATEGORIES.get(record.get('category','other'),CATEGORIES['other'])+f'/file-{index+1:03d}'+record['suffix']
