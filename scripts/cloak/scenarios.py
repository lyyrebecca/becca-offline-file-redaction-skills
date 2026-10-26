"""Purpose-driven presets; local-only configuration, never an authorization grant."""
from __future__ import annotations
from dataclasses import dataclass,asdict
ROLES={'lawyer':'律师','judge':'法官 / 法院工作人员','counsel':'企业法务','student':'学生 / 研究者','seeker':'寻求法律意见的人','other':'其他 / 暂不选择'}
PURPOSES={'ai':'交给 AI 分析','external':'给外部人员审阅','classroom':'课堂展示','students':'分发给学生','public':'公开分享'}
RECIPIENTS={'cloud_ai':'AI 服务','external':'外部人员','team':'内部协作人员','students':'学生','public':'公开公众','self':'仅自己'}
ROLE_HINTS={'lawyer':['诉讼文书','合同协议','证据材料','裁判材料'],'judge':['裁判材料','程序材料','证据材料','教学课件'],'counsel':['合同协议','交易资料','员工客户资料','调查材料'],'student':['教学课件','案例材料','研究资料'],'seeker':['聊天截图','合同协议','转账流水','通知材料'],'other':['自动识别材料性质']}
@dataclass
class Scenario:
    role:str='other'
    purpose:str='ai'
    recipient:str='cloud_ai'
    organization:str='auto'
    export_md:bool=True
    ppt_pdf:bool=False
    preserve_dates:bool=True
    preserve_amounts:bool=True
    custom_context:str=''
    def dict(self):return asdict(self)
    @property
    def policy(self):return 'public' if (self.purpose=='public' or self.recipient=='public') else 'ai' if self.purpose=='ai' else 'external'
    @property
    def clean_student_copy(self):return self.purpose=='students' or self.recipient=='students'

def scenario_from(data=None):
    data=dict(data or {});purpose=data.get('purpose','ai')
    public_target=purpose=='public' or data.get('recipient')=='public'
    defaults={'recipient':{'ai':'cloud_ai','external':'external','classroom':'self','students':'students','public':'public'}.get(purpose,'external'),'export_md':purpose=='ai','preserve_dates':not public_target,'preserve_amounts':not public_target}
    allowed=set(Scenario.__dataclass_fields__)
    if set(data)-allowed:raise ValueError('SCENARIO_INVALID')
    for name in ['export_md','ppt_pdf','preserve_dates','preserve_amounts']:
        if name in data and type(data[name]) is not bool:raise ValueError('SCENARIO_INVALID')
    s=Scenario(**(defaults|data))
    if s.role not in ROLES or s.purpose not in PURPOSES or s.recipient not in RECIPIENTS or s.organization not in ('auto','single','multi'):raise ValueError('SCENARIO_INVALID')
    if not isinstance(s.custom_context,str) or len(s.custom_context)>3000:raise ValueError('SCENARIO_INVALID')
    return s

def suggest_purpose(text):
    text=text.strip()
    for purpose,words in [('students',['学生','课件分发','发课件']),('classroom',['授课','讲课','课堂','讲座']),('ai',['AI','ai','大模型','人工智能']),('public',['公开','小红书','公众号','发布']),('external',['律师','同事','审阅','发给别人'])]:
        if any(w in text for w in words):return purpose
    return 'external'
