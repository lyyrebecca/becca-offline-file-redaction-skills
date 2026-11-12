from __future__ import annotations
import dataclasses, os, re, unicodedata
from functools import lru_cache
from pathlib import Path
from collections import Counter

TOKEN = re.compile(r'\[P:[a-f0-9]{12}:[A-Z_]+:\d{3,}\]')
KINDS = {'PERSON','ORG','ADDRESS','PHONE','EMAIL','ID','PASSPORT','SOCIAL','IP','ACCOUNT','CREDIT_CODE','CASE','CONTRACT','PROJECT','SECRET','VEHICLE','PROPERTY','HEALTH','MINOR','DATE','AMOUNT','ROLE','QUASI','CREDENTIAL','INTERNAL_PATH','REVIEW_CODE'}
HIGH = {'ID','PASSPORT','SOCIAL','IP','ACCOUNT','CREDIT_CODE','CREDENTIAL','INTERNAL_PATH','MINOR','HEALTH','SECRET','PHONE','EMAIL','ADDRESS'}
LABELS = {'PERSON':'自然人','ORG':'组织','ADDRESS':'地址','PHONE':'电话','EMAIL':'邮箱','ID':'身份证件','PASSPORT':'护照 / 通行证','SOCIAL':'社交账号','IP':'网络地址','ACCOUNT':'金融账户','CREDIT_CODE':'统一信用代码','CASE':'案号','CONTRACT':'合同编号','PROJECT':'项目','SECRET':'机密','VEHICLE':'车牌','PROPERTY':'产权','HEALTH':'健康信息','MINOR':'未成年人','DATE':'日期','AMOUNT':'金额','ROLE':'案件角色','QUASI':'间接身份线索','CREDENTIAL':'访问凭证','INTERNAL_PATH':'内部路径','REVIEW_CODE':'待确认数字 / 编码'}
OPTIONAL_REVIEW_RULES={'optional_numeric_or_code'}

# The local Chinese model labels ordinary legal-document words, font names and one-character
# place fragments as entities. Those are not identifying information and must not be masked.
NER_STOPWORDS=frozenset('''承担 负担 甲方 乙方 原告 被告 第三人 申请人 被申请人 代理人 证人 手机号
电话 联系方式 合法权益 权益 以下 上述 本人 该 本案 宋体 黑体 仿宋 楷体 微软雅黑 字体
页眉 页脚 正文 附件 备注 说明 合计 小计 序号 金额 日期 版本 状态 类型 内容 名称
事项 编号 项目 法定代表人 负责人 账户 密码 验证码 科技有限公司 有限公司'''.split())
FONT_WORDS=frozenset({'宋体','黑体','仿宋','楷体','微软雅黑','Calibri','Times New Roman'})
GENERIC_ORG=frozenset({'科技有限公司','有限公司','股份有限公司','分公司','集团公司','有限责任公司','事务所'})
COMMON_SURNAMES='赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程邢裴陆荣荀羊惠甄曲家封芮储靳松井段富焦侯全班仰秋仲伊宫宁仇甘厉戎祖武符景詹龙叶司黎白蒲乔温庄晏柴阎慕连习翟谭劳姬申冉郦桑桂牛边燕浦农尚欧聂晁辛饶曾权游盖益桓'
ADDRESS_FEATURE=re.compile(r'(路|街|巷|号|室|栋|幢|单元|层|楼|省|市|州|区|县|镇|乡|村|旗|大厦|广场|中心|花园|苑|里|弄|园区|开发区)')
ORG_FEATURE=re.compile(r'(公司|集团|银行|事务所|法院|检察院|中心|局|厅|部|院|厂|社|协会|学校|大学|医院|支队|大队)')

def plausible_entity(kind,value):
    """Reject low-quality local NER / role-rule matches that are not identifying entities."""
    v=value.strip()
    if not 2<=len(v)<=90:return False
    if v in NER_STOPWORDS or v in FONT_WORDS:return False
    if kind=='ADDRESS':
        compact=re.sub(r'\s+','',v)
        if re.search(r'''[\(\)（）\[\]【】<>《》,，。;；:：!！?？"'\\/]''',compact):return False
        return len(compact)>=4 and bool(ADDRESS_FEATURE.search(compact))
    if re.search(r'''[\s\(\)（）\[\]【】<>《》,，。;；:：!！?？"'\\/]''',v):return False
    if kind=='PERSON':
        if not re.fullmatch(r'[\u4e00-\u9fff·]{2,4}',v):return False
        return not any(w in v for w in ('承担','负担','权益','手机','甲方','乙方','以下','上述','合法','的','向','款','项','号','费','金'))
    if kind=='ORG':
        return v not in GENERIC_ORG and len(v)>=3 and bool(ORG_FEATURE.search(v))
    return True

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

def ner_text(text):
    norm=''.join(unicodedata.normalize('NFKC',c) if len(unicodedata.normalize('NFKC',c))==1 else c for c in text)
    # Random task IDs are machine syntax, not semantic context; preserve offsets with stable labels.
    return TOKEN.sub(lambda m:('<'+m.group().split(':')[2]+'>').ljust(len(m.group())),norm)

@lru_cache(maxsize=1)
def local_model():
    import spacy
    # A vendored or unpacked model directory wins over the installed package name, so a
    # blocked download can be replaced by a local copy on any platform.
    override=os.environ.get('LPC_SPACY_MODEL','').strip()
    source=override if override and Path(override).exists() else 'zh_core_web_sm'
    model=spacy.load(source,disable=['parser','tagger','attribute_ruler','lemmatizer'])
    model.max_length=2_000_000
    return model

class Detector:
    def __init__(self, policy='ai', dictionary=None, use_ner=True):
        if policy not in ('ai','external','public'): raise ValueError('POLICY_INVALID')
        self.policy=policy;self.dictionary=dictionary or {};self.nlp=None;self.ner_available=False;self.ner_error='';self._results={};self._entities={};self.preserve_dates=policy!='public';self.preserve_amounts=policy!='public'
        if use_ner:
            try:
                self.nlp=local_model();self.ner_available=True
            except (ImportError,OSError) as exc:
                # Keep the reason as a code only: exception text can include local paths.
                self.ner_error=type(exc).__name__
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
            norms=[ner_text(t) for t in values]
            for text,doc in zip(values,self.nlp.pipe(norms,batch_size=64)):
                self._entities[text]=[(e.start_char,e.end_char,e.label_,e.text) for e in doc.ents]

    def find(self,text):
        if text in self._results:return [dataclasses.replace(h) for h in self._results[text]]
        # Normalize for detection while preserving original character offsets (including OCR/fullwidth digits).
        norm=''.join((unicodedata.normalize('NFKC',c) if len(unicodedata.normalize('NFKC',c))==1 else c) for c in text)
        hits=[]
        protected=[(m.start(),m.end()) for m in TOKEN.finditer(norm)]
        protected.extend(m.span() for m in re.finditer(r'(?<![A-Za-z0-9_-])(?:u\d{6}|file-\d{3})(?![A-Za-z0-9_-])',norm))
        def add(s,e,k,r,c=1.0,entity='',mask=True,reason=''):
            if re.fullmatch(r'\*{3,}',norm[s:e]):return
            if s<e and not any(s<b and e>a for a,b in protected):hits.append(Hit(s,e,k,r,c,mask,reason,entity))
        rules=[
          ('PHONE',r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)','cn_mobile'),
          ('PHONE',r'(?<!\d)(?:0\d{2,3}[- ]?)\d{7,8}(?!\d)','cn_landline'),
          ('EMAIL',r'[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','email'),
          ('ID',r'(?<!\d)\d{17}[\dXx](?!\d)','cn_id_candidate'),
          # Structured identifiers: these have a recognisable shape or an explicit field
          # label, so they are masked automatically instead of waiting for manual review.
          ('ID',r'(?<!\d)\d{8}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}(?!\d)','legacy_id_15'),
          ('ID',r'(?:执业证号|律师执业证号|执业证书编号|执业证编号)[：:\s]*(\d{13,20})','license_context'),
          ('ACCOUNT',r'(?:账号|帐号|账户|银行卡号|卡号|开户账号|收款账号|银行账号)[：:\s]*(\d[\d\- ]{12,26}\d)','account_context'),
          ('CREDIT_CODE',r'(?<![A-Z0-9])[0-9A-HJ-NPQRTUWXY]{18}(?![A-Z0-9])','credit_code_candidate'),
          ('CREDIT_CODE',r'(?:统一社会信用代码|营业执照注册号|企业注册号|注册号)[：:\s]*([0-9A-Za-z][0-9A-Za-z\-]{13,21}[0-9A-Za-z])','credit_code_context'),
          ('CONTRACT',r'(?:报告编号|项目编号|文档编号|卷宗编号)[：:\s]*([A-Za-z0-9][A-Za-z0-9_\-/]{4,40})','document_number_context'),
          ('ACCOUNT',r'(?<!\d)\d{15,19}(?!\d)','bank_account_length'),
          ('PASSPORT',r'(?:护照号|护照号码|港澳通行证号|台湾居民来往大陆通行证号)[：:\s]*([A-Z][A-Z0-9]{7,11})','travel_document_context'),
          ('SOCIAL',r'(?:微信号|微信ID|QQ号|社交账号|社交平台账号)[：:\s]*([A-Za-z0-9_-]{5,30})','social_account_context'),
          ('IP',r'(?:登录IP|客户端IP|公网IP|IP地址)[：:\s]*((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3})','ip_address_context'),
          ('CASE',r'[（(]\d{4}[）)][\u4e00-\u9fffA-Za-z0-9]{1,15}?\d{1,8}号','case_number'),
          ('CONTRACT',r'(?:合同编号|协议编号)[：:\s]*([A-Za-z0-9_\-/]{3,60})','contract_context'),
          ('PROJECT',r'(?:项目代号|项目名称|代号)[：:\s]*([^，。；;<>\n\t]{2,30})','project_context'),
          ('ADDRESS',r'(?:住所地|通讯地址|通信地址|居住地址|居住地|户籍地址|家庭住址|家庭地址|联系地址|常住地址|登记地址|注册地址|收件地址|工作地址|住址|地址|所在地)[：:\s]*([^，。；;<>\n\t]{3,90})','address_context'),
          ('ADDRESS',r'(?<![\u4e00-\u9fff])((?:[\u4e00-\u9fff]{2,8}(?:省|自治区|特别行政区))?(?:[\u4e00-\u9fff]{2,8}(?:市|州|地区|盟))?[\u4e00-\u9fff]{2,8}(?:区|县|旗)[\u4e00-\u9fff\dA-Za-z·-]{1,20}(?:路|街|巷|弄|道|胡同)\d{0,6}(?:号)?(?:[\u4e00-\u9fff\dA-Za-z·-]{0,16}(?:栋|幢|号楼|单元|室|层|楼))?)','structured_address'),
          ('PERSON',r'(?:姓名|自然人姓名|当事人|原告|被告|被告人|第三人|申请人|被申请人|上诉人|被上诉人|再审申请人|申请执行人|被执行人|委托人|受托人|证人|犯罪嫌疑人|法定代表人|负责人|代理人|委托代理人|诉讼代理人|联系人|经办人|承办人|接收人|收款人|付款人|律师|法官|审判员)[：:\s]*([\u4e00-\u9fff·]{2,4})(?=[，。；;、（）()【】\[\]<>：:\s]|$)','person_role'),
          ('PERSON',rf'(?:(?<![\u4e00-\u9fff])([{COMMON_SURNAMES}][\u4e00-\u9fff]{{1,2}}?)(?=(?:先生|女士|律师|法官|原告|被告|起诉|应诉|签署|签订|提交|出具|委托|代理|确认|同意|申请|与|诉|于|在|等))|(?<=[与及、诉])([{COMMON_SURNAMES}][\u4e00-\u9fff]{{1,2}}?)(?=[，。；;、：:\s]|$))','person_legal_context'),
          ('VEHICLE',r'(?<![A-Za-z0-9])[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][·•\-\s]?[A-HJ-NP-Z0-9]{5,7}(?![A-Za-z0-9])','vehicle'),
          ('PROPERTY',r'(?:产权证号|不动产权证号|房产证号)[：:\s]*([^，。；;<>\n\t]{3,60})','property_context'),
          ('CREDENTIAL',r'(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|passwd|pwd|密码|令牌|密钥|验证码|token|secret)[：:=\s]+([A-Za-z0-9_\-./+]{4,})','credential_context'),
          ('INTERNAL_PATH',r"(?i)(?:\\\\[A-Za-z0-9._-]+\\[A-Za-z0-9$._ -]+(?:\\[^\s<>:\"|?*]+)*|[A-Za-z]:\\(?:Users|Documents and Settings|Profiles|ProgramData)\\[^\s<>:\"|?*]+(?:\\[^\s<>:\"|?*]+)*|/(?:Users|home|private/var|srv|mnt|data)/[A-Za-z0-9._-]+(?:/[^\s<>:\"|?*]+)+|smb://[^\s<>\"']+)", 'internal_path'),
          ('MINOR',r'(?:\d{1,2}岁(?:的)?未成年人|未满十四周岁|不满十四周岁)','minor_context'),
          ('HEALTH',r'(?:诊断为|患有|病史)[：:\s]*([^，。；;<>\n\t]{2,30})','health_context'),
          ('QUASI',r'(?:唯一.{0,12}(?:创始人|股东|负责人)|持有\s*\d+(?:\.\d+)?%\s*股权|[\u4e00-\u9fff]{2,4}(?:的女儿|的儿子|的配偶))','quasi_context'),
          ('REVIEW_CODE',r'(?<!\d)\d{6,32}(?!\d)','optional_numeric_or_code'),
          ('REVIEW_CODE',r'(?<![A-Za-z0-9_-])(?=[A-Za-z0-9_-]{6,32}(?![A-Za-z0-9_-]))(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]+(?![A-Za-z0-9_-])','optional_numeric_or_code'),
        ]
        if not self.preserve_dates:rules.append(('DATE',r'\d{4}(?:年|[-/])\d{1,2}(?:月|[-/])\d{1,2}日?','purpose_date'))
        if not self.preserve_amounts:rules.append(('AMOUNT',r'\d+(?:\.\d+)?\s*(?:亿元|万元|元)','purpose_amount'))
        for k,pat,r in rules:
            for m in re.finditer(pat,norm):
                if r=='person_legal_context':s,e=m.span(1) if m.group(1) is not None else m.span(2)
                else:s,e=m.span(1) if m.lastindex else m.span()
                rr=r;value=norm[s:e]
                if k=='CREDIT_CODE' and r=='credit_code_context':
                    normalized=value.replace('-','').replace(' ','')
                    if not 15<=len(normalized)<=20 or not re.search(r'[A-Za-z]',normalized):continue
                if k=='PERSON' and r=='person_role' and not plausible_entity(k,value):continue
                if k=='PERSON' and r=='person_legal_context' and not plausible_entity(k,value):continue
                if k=='ID' and r=='cn_id_candidate':rr='cn_id_checksum' if id_checksum(value) else 'cn_id_invalid_checksum_review'
                if k=='REVIEW_CODE':add(s,e,k,rr,0.35,mask=False,reason='待确认的连续数字/编码候选；默认不打码，请结合上下文选择。')
                elif k=='PERSON' and r=='person_legal_context':add(s,e,k,rr,0.72)
                else:add(s,e,k,rr)
        for m in re.finditer(r'(?<!\d)\d{16,19}(?!\d)',norm):
            if luhn(m.group()):add(m.start(),m.end(),'ACCOUNT','luhn')
        for item in self.terms:
            for m in re.finditer(re.escape(item['text']),text):add(*m.span(),item['kind'],'case_dictionary',entity=item.get('entity',''))
        if self.nlp and re.search(r'[\u4e00-\u9fff]',norm):
            entities=self._entities.get(text)
            if entities is None:entities=[(e.start_char,e.end_char,e.label_,e.text) for e in self.nlp(ner_text(norm)).ents]
            for start,end,label,value in entities:
                k={'PERSON':'PERSON','PER':'PERSON','ORG':'ORG','GPE':'ADDRESS','LOC':'ADDRESS'}.get(label)
                if not k:continue
                if k=='ORG' and self.policy!='public' and re.search(r'(人民法院|人民检察院)$',value):continue
                if not plausible_entity(k,value):continue
                add(start,end,k,'local_zh_ner',0.75)
        # Prefer explicit dictionary and longer spans. Do not let NER shorten a deterministic match.
        hits.sort(key=lambda h:(h.rule!='case_dictionary',h.rule in OPTIONAL_REVIEW_RULES,h.rule=='local_zh_ner',-(h.end-h.start),h.start))
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
