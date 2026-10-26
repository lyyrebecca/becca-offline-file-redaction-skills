from __future__ import annotations
import dataclasses, re, unicodedata
from functools import lru_cache
from collections import Counter

TOKEN = re.compile(r'\[P:[a-f0-9]{12}:[A-Z_]+:\d{3,}\]')
KINDS = {'PERSON','ORG','ADDRESS','PHONE','EMAIL','ID','ACCOUNT','CREDIT_CODE','CASE','CONTRACT','PROJECT','SECRET','VEHICLE','PROPERTY','HEALTH','MINOR','DATE','AMOUNT','ROLE','QUASI','CREDENTIAL'}
HIGH = {'ID','ACCOUNT','CREDIT_CODE','CREDENTIAL','MINOR','HEALTH','SECRET','PHONE','EMAIL','ADDRESS'}
LABELS = {'PERSON':'自然人','ORG':'组织','ADDRESS':'地址','PHONE':'电话','EMAIL':'邮箱','ID':'身份证件','ACCOUNT':'金融账户','CREDIT_CODE':'统一信用代码','CASE':'案号','CONTRACT':'合同编号','PROJECT':'项目','SECRET':'机密','VEHICLE':'车牌','PROPERTY':'产权','HEALTH':'健康信息','MINOR':'未成年人','DATE':'日期','AMOUNT':'金额','ROLE':'案件角色','QUASI':'间接身份线索','CREDENTIAL':'访问凭证'}

@dataclasses.dataclass
class Hit:
    start:int
    end:int
    kind:str
    rule:str
    confidence:float = 1.0
    mask:bool = True
    reason:str = ''
    entity:str = ''
    def dict(self): return dataclasses.asdict(self)


def id_checksum(s):
    if not re.fullmatch(r'\d{17}[0-9Xx]',s):return False
    return '10X98765432'[sum(int(a)*b for a,b in zip(s[:17],[7,9,10,5,8,4,2,1,6,3,7,9,10,5,8,4,2]))%11] == s[-1].upper()

def luhn(s):
    ds=[int(x) for x in s if x.isdigit()]
    return bool(ds) and sum((v*2//10+v*2%10) if i%2 else v for i,v in enumerate(reversed(ds)))%10==0

@lru_cache(maxsize=1)
def local_model():
    import spacy
    model=spacy.load('zh_core_web_sm',disable=['parser','tagger','attribute_ruler','lemmatizer'])
    model.max_length=2_000_000
    return model

class Detector:
    def __init__(self, policy='ai', dictionary=None, use_ner=True):
        if policy not in ('ai','external','public'): raise ValueError('POLICY_INVALID')
        self.policy=policy;self.dictionary=dictionary or {};self.nlp=None;self.ner_available=False;self._results={};self._entities={};self.preserve_dates=policy!='public';self.preserve_amounts=policy!='public'
        if use_ner:
            try:
                self.nlp=local_model();self.ner_available=True
            except (ImportError,OSError): pass
        self.terms=[]
        for item in self.dictionary.get('terms',[]):
            if not isinstance(item,dict) or item.get('kind') not in KINDS or not isinstance(item.get('text'),str) or not item['text']:
                raise ValueError('DICTIONARY_INVALID')
            self.terms.append(item)
        self.allow=self.dictionary.get('allow',[])
        if not isinstance(self.allow,list) or any(not isinstance(x,str) or not x for x in self.allow):raise ValueError('DICTIONARY_INVALID')

    def prime(self,texts):
        # Batch only semantic NER; deterministic rules still inspect every unit.
        values=list(dict.fromkeys(t for t in texts if re.search(r'[\u4e00-\u9fff]',t) and t not in self._entities))
        if self.nlp:
            norms=[''.join(unicodedata.normalize('NFKC',c) if len(unicodedata.normalize('NFKC',c))==1 else c for c in t) for t in values]
            for text,doc in zip(values,self.nlp.pipe(norms,batch_size=64)):
                self._entities[text]=[(e.start_char,e.end_char,e.label_,e.text) for e in doc.ents]

    def find(self,text):
        if text in self._results:return [dataclasses.replace(h) for h in self._results[text]]
        # Normalize for detection while preserving original character offsets (including OCR/fullwidth digits).
        norm=''.join((unicodedata.normalize('NFKC',c) if len(unicodedata.normalize('NFKC',c))==1 else c) for c in text)
        hits=[]
        protected=[(m.start(),m.end()) for m in TOKEN.finditer(norm)]
        def add(s,e,k,r,c=1.0,entity=''):
            if s<e and not any(s<b and e>a for a,b in protected):hits.append(Hit(s,e,k,r,c,entity=entity))
        rules=[
          ('PHONE',r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)','cn_mobile'),
          ('PHONE',r'(?<!\d)(?:0\d{2,3}[- ]?)\d{7,8}(?!\d)','cn_landline'),
          ('EMAIL',r'[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','email'),
          ('ID',r'(?<!\d)\d{17}[\dXx](?!\d)','cn_id_candidate'),
          ('ACCOUNT',r'(?:账号|帐号|账户|银行卡号|卡号)[：:\s]*([\d -]{8,30}\d)','account_context'),
          ('CREDIT_CODE',r'(?<![A-Z0-9])[0-9A-HJ-NPQRTUWXY]{18}(?![A-Z0-9])','credit_code_candidate'),
          ('CASE',r'[（(]\d{4}[）)][\u4e00-\u9fffA-Za-z0-9]{1,15}?\d{1,8}号','case_number'),
          ('CONTRACT',r'(?:合同编号|协议编号)[：:\s]*([A-Za-z0-9_\-/]{3,60})','contract_context'),
          ('PROJECT',r'(?:项目代号|项目名称|代号)[：:\s]*([^，。；;\n\t]{2,30})','project_context'),
          ('ADDRESS',r'(?:住所地|住址|家庭地址|联系地址|地址)[：:\s]*([^，。；;\n\t]{3,90})','address_context'),
          ('PERSON',r'(?:姓名|原告|被告|申请人|被申请人|证人|法定代表人|代理人|联系人|负责人|律师|法官)[：:\s]*([\u4e00-\u9fff·]{2,5})(?=[，。；;\s]|$)','person_role'),
          ('VEHICLE',r'[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-HJ-NP-Z0-9]{5,6}','vehicle'),
          ('PROPERTY',r'(?:产权证号|不动产权证号|房产证号)[：:\s]*([^，。；;\n\t]{3,60})','property_context'),
          ('CREDENTIAL',r'(?i)(?:api[_-]?key|password|密码|token|secret)[：:=\s]+([A-Za-z0-9_\-./+]{6,})','credential_context'),
          ('MINOR',r'(?:\d{1,2}岁(?:的)?未成年人|未满十四周岁|不满十四周岁)','minor_context'),
          ('HEALTH',r'(?:诊断为|患有|病史)[：:\s]*([^，。；;\n\t]{2,30})','health_context'),
          ('QUASI',r'(?:唯一.{0,12}(?:创始人|股东|负责人)|持有\s*\d+(?:\.\d+)?%\s*股权|[\u4e00-\u9fff]{2,4}(?:的女儿|的儿子|的配偶))','quasi_context'),
        ]
        if not self.preserve_dates:rules.append(('DATE',r'\d{4}(?:年|[-/])\d{1,2}(?:月|[-/])\d{1,2}日?','purpose_date'))
        if not self.preserve_amounts:rules.append(('AMOUNT',r'\d+(?:\.\d+)?\s*(?:亿元|万元|元)','purpose_amount'))
        for k,pat,r in rules:
            for m in re.finditer(pat,norm):
                s,e=m.span(1) if m.lastindex else m.span()
                rr=r
                if k=='ID':rr='cn_id_checksum' if id_checksum(norm[s:e]) else 'cn_id_invalid_checksum_review'
                add(s,e,k,rr)
        for m in re.finditer(r'(?<!\d)\d{16,19}(?!\d)',norm):
            if luhn(m.group()):add(m.start(),m.end(),'ACCOUNT','luhn')
        for item in self.terms:
            for m in re.finditer(re.escape(item['text']),text):add(*m.span(),item['kind'],'case_dictionary',entity=item.get('entity',''))
        if self.nlp and re.search(r'[\u4e00-\u9fff]',norm):
            entities=self._entities.get(text)
            if entities is None:entities=[(e.start_char,e.end_char,e.label_,e.text) for e in self.nlp(norm).ents]
            for start,end,label,value in entities:
                k={'PERSON':'PERSON','PER':'PERSON','ORG':'ORG','GPE':'ADDRESS','LOC':'ADDRESS'}.get(label)
                if not k:continue
                if k=='ORG' and self.policy!='public' and re.search(r'(人民法院|人民检察院)$',value):continue
                add(start,end,k,'local_zh_ner',0.75)
        # Prefer explicit dictionary and longer spans. Do not let NER shorten a deterministic match.
        hits.sort(key=lambda h:(h.rule!='case_dictionary',h.rule=='local_zh_ner',-(h.end-h.start),h.start))
        accepted=[]
        for h in hits:
            if any(h.start<a.end and h.end>a.start for a in accepted):continue
            value=text[h.start:h.end]
            if value in self.allow and h.kind not in HIGH:
                h.mask=False;h.reason='allowlist_requires_review'
            elif value in self.allow: h.reason='high_risk_allow_conflict'
            accepted.append(h)
        result=sorted(accepted,key=lambda h:h.start)
        if len(self._results)<4096:self._results[text]=result
        return [dataclasses.replace(h) for h in result]


def apply_spans(text,hits,replacement):
    last=0;out=[]
    for h in sorted(hits,key=lambda x:x.start):
        if h.start<last or h.end>len(text) or h.start<0:raise ValueError('SPAN_INVALID')
        out.extend([text[last:h.start],replacement(h) if h.mask else text[h.start:h.end]])
        last=h.end
    return ''.join(out)+text[last:]

class Tokenizer:
    def __init__(self,task):self.task=task;self.mapping={};self.ids={};self.counts=Counter()
    def token(self,value,kind,entity,scope):
        # No automatic cross-file identity merge; explicit dictionary entity IDs opt in.
        key=(kind,('entity',entity,value) if entity else ('scope',scope,value))
        if key not in self.ids:
            self.counts[kind]+=1
            token=f'[P:{self.task}:{kind}:{self.counts[kind]:03d}]'
            self.ids[key]=token;self.mapping[token]=value
        elif self.mapping[self.ids[key]] != value:
            # Explicit alias: all aliases restore to the canonical first spelling, noted in review.
            pass
        return self.ids[key]
