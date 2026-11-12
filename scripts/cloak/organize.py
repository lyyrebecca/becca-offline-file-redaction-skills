"""Single-case batch defaults and stable output names; no per-file classification UI."""
import re

CATEGORIES={'pleadings':'01_诉讼文书','contracts':'02_合同协议','evidence':'03_证据材料','decisions':'04_裁判程序','slides':'05_教学课件','research':'06_通用研究','other':'07_其他材料'}


def propose(files,organization='single'):
    """Assign every uploaded file in one task to the same internal case alias."""
    if organization!='single':
        raise ValueError('SCENARIO_INVALID')
    seen={}
    for i,f in enumerate(files):
        f['category']='other'
        f['duplicate_of']=seen.get(f['sha256'])
        seen.setdefault(f['sha256'],i)
        f['group_reason']='本批所有文件统一归入同一案件'
        f['case_id']='CASE001'
    return {'case_count':1 if files else 0,'pending':0,'duplicates':sum(f['duplicate_of'] is not None for f in files)}


def set_assignments(job,assignments):
    """Compatibility helper for explicit local test fixtures and legacy task migration."""
    if not isinstance(assignments,list) or len(assignments)!=len(job['files']):
        raise ValueError('GROUP_ASSIGNMENT_INVALID')
    seen=set()
    for row in assignments:
        i=row['index'];case=row['case_id']
        if type(i) is not int or not 0<=i<len(job['files']) or i in seen:
            raise ValueError('GROUP_ASSIGNMENT_INVALID')
        seen.add(i);category=row.get('category',job['files'][i].get('category','other'))
        if not isinstance(case,str) or not re.fullmatch(r'CASE\d{3}|COMMON|PENDING',case) or category not in CATEGORIES:
            raise ValueError('GROUP_ASSIGNMENT_INVALID')
    for row in assignments:
        f=job['files'][row['index']]
        f['case_id']=row['case_id'];f['category']=row.get('category',f.get('category','other'))
    job['groups_confirmed']=True;job['reviewed']=False;job['status']='NEEDS_REVIEW'


def relative_name(record,index):
    case=record.get('case_id','CASE001')
    folder='案件'+case[4:] if isinstance(case,str) and re.fullmatch(r'CASE\d{3}',case) else '案件001'
    return folder+f'/file-{index+1:03d}'+record['suffix']
