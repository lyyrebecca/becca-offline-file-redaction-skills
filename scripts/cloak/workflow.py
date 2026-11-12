from __future__ import annotations
import collections, hashlib, json, os, re, secrets, zipfile, io
from pathlib import Path
from datetime import datetime
from . import __version__
from .core import Detector, Hit, Tokenizer, TOKEN, HIGH, KINDS
from .formats import Document, change_nodes, SUPPORTED
from .table_fields import contextual_hits
from .vault import seal,open_vault,atomic,b64,unb64
from .platform_support import secure_dir, shanghai_tz
from .issues import SOFT_ISSUES, issue_details, required_soft_confirmations, structural_blockers

POLICY_VERSION='2026-11-09.1'
def now():return datetime.now(shanghai_tz()).isoformat(timespec='seconds')

def digest(data):return hashlib.sha256(data).hexdigest()
def hits_from(obj):return [Hit(**x) for x in obj]
def publish(path,obj):atomic(path,(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode())
def make_detector(job):
    d=Detector(job['policy'],job['dictionary'])
    if job.get('scenario'):
        d.preserve_dates=job['scenario']['preserve_dates'];d.preserve_amounts=job['scenario']['preserve_amounts']
    return d

def detector_for_suffix(detector,suffix):
    if suffix.lower()!='.xml':return detector
    # Raw XML includes tag/attribute names; generic NER can misclassify those labels and corrupt markup.
    d=Detector(detector.policy,detector.dictionary,use_ner=False)
    d.preserve_dates=detector.preserve_dates;d.preserve_amounts=detector.preserve_amounts
    return d
def require_ner(detector):
    """Fail closed unless the user explicitly opted into rule-only detection."""
    if detector.ner_available:return False
    try:
        from runtime import allow_rule_only
        allowed=allow_rule_only()
    except ImportError:
        allowed=os.environ.get('LPC_ALLOW_RULE_ONLY','').strip().lower() in ('1','true','yes','on')
    if not allowed:raise ValueError('LOCAL_NER_UNAVAILABLE')
    return True

def propagate_same_file_literals(units):
    """Turn repeated exact sensitive literals into reviewable candidates within one file only."""
    structured={'ID','PASSPORT','SOCIAL','IP','ACCOUNT','CREDIT_CODE','CREDENTIAL','INTERNAL_PATH','PHONE','EMAIL','CASE','CONTRACT','VEHICLE','PROPERTY'}
    descriptive={'PERSON','ORG','ADDRESS','PROJECT','SECRET','HEALTH','MINOR'}
    priority={'ID':10,'ACCOUNT':9,'CREDIT_CODE':9,'PASSPORT':9,'CREDENTIAL':9,'INTERNAL_PATH':9,'PHONE':8,'EMAIL':8,'IP':8,'SOCIAL':8,'CASE':7,'CONTRACT':7,'VEHICLE':7,'PROPERTY':7}
    seed_kinds={}
    for unit in units:
        if unit['kind'] not in ('text','ocr'):continue
        for hit in unit['hits']:
            if not hit.get('mask',True):continue
            value=unit['text'][hit['start']:hit['end']]
            if hit['kind'] in structured and len(value)>=5 or hit['kind'] in descriptive and len(value)>=3:
                if value not in seed_kinds or priority.get(hit['kind'],1)>priority.get(seed_kinds[value],1):seed_kinds[value]=hit['kind']
    if not seed_kinds:return
    seeds=sorted(seed_kinds.items(),key=lambda x:(-len(x[0]),-priority.get(x[1],1),x[0]))
    import re
    for unit in units:
        if unit['kind'] not in ('text','ocr'):continue
        for value,kind in seeds:
            for match in re.finditer(re.escape(value),unit['text']):
                overlaps=[h for h in unit['hits'] if match.start()<h['end'] and match.end()>h['start']]
                if overlaps and all(h['kind']=='REVIEW_CODE' and not h.get('mask',False) for h in overlaps):
                    unit['hits']=[h for h in unit['hits'] if h not in overlaps]
                elif overlaps:continue
                unit['hits'].append(Hit(match.start(),match.end(),kind,'same_file_exact_literal',0.95).dict())
        unit['hits'].sort(key=lambda h:(h['start'],h['end']))

def stats(job,status=None):
    counts=collections.Counter(h['kind'] for f in job['files'] for u in f['units'] for h in u['hits'] if h['mask'])
    return {'version':job.get('version','1.0.0'),'task':job['task'],'policy':job['policy'],'policy_version':POLICY_VERSION,
      'status':status or job['status'],'file_count':len(job['files']),'masked_candidates':dict(counts),
      'reviewed':job.get('reviewed',False),'issues':sorted(set(i for f in job['files'] for i in f['issues'])),
      'ner':job.get('ner',True),
      'kept_candidates':sum(not h['mask'] for f in job['files'] for u in f['units'] for h in u['hits']),
      'files':[{'index':i,'format':f['suffix'],'candidate_count':sum(len(u['hits']) for u in f['units'])} for i,f in enumerate(job['files'])]}

def scan(paths,workspace,password,policy='ai',dictionary=None,scenario=None,progress=None):
    ws=Path(workspace).resolve()
    if ws.exists() and any(ws.iterdir()):raise ValueError('WORKSPACE_NOT_EMPTY')
    secure_dir(ws);secure_dir(ws/'private')
    from .scenarios import scenario_from
    config=scenario_from(scenario) if scenario is not None else None
    if config:policy=config.policy
    detector=Detector(policy,dictionary);rule_only=require_ner(detector)
    if config:detector.preserve_dates=config.preserve_dates;detector.preserve_amounts=config.preserve_amounts
    task=secrets.token_hex(6)
    job={'task':task,'policy':policy,'policy_version':POLICY_VERSION,'created_at':now(),'dictionary':dictionary or {},'status':'NEEDS_REVIEW','reviewed':False,'files':[],'mapping':{},'approved_issues':[],'ner':not rule_only}
    if config:job.update(version=__version__,scenario=config.dict(),groups_confirmed=True)
    resolved=[Path(p).resolve(strict=True) for p in paths]
    if not resolved or len(resolved)>100:raise ValueError('BATCH_LIMIT')
    if len(set(resolved))!=len(resolved):raise ValueError('DUPLICATE_INPUT')
    for i,p in enumerate(resolved):
        if p.suffix.lower() not in SUPPORTED:raise ValueError('FORMAT_UNSUPPORTED')
        if p.stat().st_size>100*1024*1024:raise ValueError('FILE_TOO_LARGE')
        if progress:progress(i,len(resolved),'scan')
        data=p.read_bytes();prepared=data;teaching={}
        # Inspect original unsupported parts before cleanup; cleanup is never a bypass.
        original_doc=Document(data,p.suffix)
        if config and config.clean_student_copy and p.suffix.lower()=='.pptx':
            from .teaching import student_copy
            prepared,teaching=student_copy(data)
        doc=original_doc if prepared==data else Document(prepared,p.suffix)
        for issue in original_doc.issues:
            if issue not in SOFT_ISSUES and issue not in doc.issues:doc.issues.append(issue)
        file_detector=detector_for_suffix(detector,p.suffix)
        file_detector.prime(u.text for u in doc.units)
        contextual=contextual_hits(doc,file_detector)

        has_formulas=any(u.kind=='formula' for u in doc.units)
        units=[]
        for u in doc.units:
            hs=file_detector.find(u.text)
            if u.kind not in ('text','ocr'):
                hs=[h for h in hs if h.kind!='REVIEW_CODE']
            for extra in contextual.get(u.key,[]):
                if not any(extra.start<h.end and extra.end>h.start for h in hs):hs.append(extra)
            hs.sort(key=lambda h:(h.start,h.end))
            structural_hits=[h for h in hs if h.kind!='REVIEW_CODE']
            if u.kind=='formula' and structural_hits:doc.issues.append('SENSITIVE_FORMULA_BLOCKED')
            if u.kind=='reference' and structural_hits:doc.issues.append('SENSITIVE_REFERENCE_BLOCKED')
            if f'{p.suffix.lower()}'=='.xlsx' and structural_hits:
                from .formats import S
                for node in u.nodes:
                    cells=[a for a in [node]+list(node.iterancestors()) if a.tag=='{'+S+'}c']
                    if cells:
                        cell=cells[0]
                        if cell.find('{'+S+'}f') is not None:doc.issues.append('SENSITIVE_FORMULA_BLOCKED')
                        elif cell.get('t') in (None,'n') and has_formulas:doc.issues.append('SENSITIVE_NUMERIC_WITH_FORMULAS')
            if not hs and u.kind not in ('text','ocr','formula'):continue
            units.append({'source_ref':u.source_ref,'key':u.key,'kind':u.kind,'text':u.text,'hits':[h.dict() for h in hs],'image':u.image,'boxes':u.boxes,'preview_cells':u.preview_cells,'field':u.field})
        # Same literal is consistently pseudonymized only within a file. Local user can link identities via dictionary IDs.
        doc.issues.append('ENTITY_AMBIGUITY_REVIEW')
        if rule_only:doc.issues.append('RULE_ONLY_DETECTION')
        if len(resolved)>1:doc.issues.append('CROSS_FILE_IDENTITY_REVIEW')
        propagate_same_file_literals(units)
        job['files'].append({'source':str(p),'suffix':p.suffix.lower(),'sha256':digest(data),'original':b64(data),'prepared':b64(prepared) if prepared!=data else None,'teaching':teaching,'units':units,'issues':sorted(set(doc.issues))})
    if config:
        from .organize import propose
        job['organization']=propose(job['files'],config.organization)
    seal(ws/'private'/'task.lpcv',job,password)
    report=stats(job);report['ner']=not rule_only
    publish(ws/'scan-report.json',report)
    return report

def review_update(job,decisions=None,confirmations=None):
    decisions=decisions or {}
    for fi,f in enumerate(job['files']):
        for ui,u in enumerate(f['units']):
            for hi,h in enumerate(u['hits']):
                key=f'{fi}:{ui}:{hi}'
                if key in decisions:
                    v=decisions[key];h['mask']=bool(v.get('mask',True));h['reason']=str(v.get('reason',''))[:300]
                if not h['mask'] and not h['reason'].strip():raise ValueError('KEEP_REQUIRES_REASON')
                if h['mask']:h['reason']='reviewed_mask'
    if job.get('scenario') and (not job.get('groups_confirmed') or any(f.get('case_id')=='PENDING' for f in job['files'])):raise ValueError('GROUP_REVIEW_REQUIRED')
    blockers=set(i for f in job['files'] for i in f['issues'])-SOFT_ISSUES
    needed=set(i for f in job['files'] for i in f['issues'])&SOFT_ISSUES
    if blockers:raise ValueError('UNRESOLVED_STRUCTURAL_BLOCKERS')
    if not needed.issubset(set(confirmations or [])):raise ValueError('LOCAL_REVIEW_INCOMPLETE')
    job['approved_issues']=sorted(needed);job['reviewed']=True;job['status']='REVIEWED';job['reviewed_at']=now()
    return job

def add_manual(job,fi,ui,start,end,kind):
    if kind not in KINDS:raise ValueError('ENTITY_KIND_INVALID')
    u=job['files'][fi]['units'][ui]
    if not 0<=start<end<=len(u['text']):raise ValueError('SPAN_INVALID')
    if any(start<h['end'] and end>h['start'] for h in u['hits']):raise ValueError('SPAN_OVERLAP')
    u['hits'].append(Hit(start,end,kind,'local_manual').dict());u['hits'].sort(key=lambda h:h['start'])
    job['reviewed']=False;job['status']='NEEDS_REVIEW'

def learn_across_task(job,value,kind):
    """Apply a user-selected exact literal to every matching text/OCR unit in this task."""
    import re
    from .core import KINDS
    if not isinstance(value,str) or not value.strip() or len(value)>500 or kind not in KINDS:raise ValueError('LEARN_VALUE_INVALID')
    value=value.strip();targets=[]
    for fi,record in enumerate(job['files']):
        for ui,unit in enumerate(record['units']):
            if unit['kind'] not in ('text','ocr'):continue
            for match in re.finditer(re.escape(value),unit['text']):targets.append((fi,ui,unit,match))
    if not targets:raise ValueError('SPAN_NOT_FOUND')
    for fi,ui,unit,match in targets:
        if any(match.start()<h['end'] and match.end()>h['start'] and (match.start(),match.end())!=(h['start'],h['end']) for h in unit['hits']):raise ValueError('SPAN_OVERLAP')
    term={'text':value,'kind':kind,'entity':''};terms=job.setdefault('dictionary',{}).setdefault('terms',[])
    if not any(x.get('text')==value and x.get('kind')==kind for x in terms):terms.append(term)
    for fi,ui,unit,match in targets:
        exact=next((h for h in unit['hits'] if (match.start(),match.end())==(h['start'],h['end'])),None)
        if exact:exact.update({'kind':kind,'rule':'local_learned_rule','confidence':0.95,'mask':True,'reason':'reviewed_mask'})
        else:unit['hits'].append(Hit(match.start(),match.end(),kind,'local_learned_rule').dict());unit['hits'].sort(key=lambda h:(h['start'],h['end']))
        job['files'][fi]['seen']=False
    job['reviewed']=False;job['status']='NEEDS_REVIEW'
    return {'occurrences':len(targets),'files':len({fi for fi,_,_,_ in targets})}

def input_data(record):return unb64(record.get('prepared') or record['original'])

def _attach(doc,record):
    units={u.key:u for u in doc.units}
    for r in record['units']:
        u=units.get(r['key'])
        if u is None or u.text!=r['text']:raise ValueError('DOCUMENT_SNAPSHOT_MISMATCH')
        u.hits=hits_from(r['hits'])


def verify_data(data,suffix,detector,kept=None,masked=None,doc=None,ignore_optional_codes=False):
    doc=doc or Document(data,suffix)
    detector=detector_for_suffix(detector,suffix)
    detector.prime(u.text for u in doc.units)
    blockers=set(doc.issues)-SOFT_ISSUES
    kept=collections.Counter(kept or {})
    residual=[]
    for u in doc.units:
        for h in detector.find(u.text):
            if h.kind=='REVIEW_CODE' and (ignore_optional_codes or u.kind not in ('text','ocr')):continue
            key=(h.kind,u.text[h.start:h.end])
            if kept[key]>0:kept[key]-=1
            else:residual.append({'unit':u.key,'kind':h.kind,'rule':h.rule})
    # Known masked originals must not survive in any extracted text, including XML metadata.
    for v in set(masked or []):
        if len(v)>=2:
            for u in doc.units:
                count=u.text.count(v)
                if count:
                    # An explicitly reviewed kept occurrence may share that literal.
                    residual.append({'unit':u.key,'kind':'RESIDUAL','rule':'known_masked_value','occurrences':count})
    # Independent metadata pass: Document intentionally clears metadata before normal extraction.
    if suffix in ('.docx','.xlsx','.pptx'):
        from lxml import etree as E
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.lower().startswith('docprops/') and name.lower().endswith('.xml'):
                    root=E.fromstring(z.read(name))
                    values=[s for s in root.itertext() if s.strip()]+[v for e in root.iter() for v in e.attrib.values()]
                    for v in values:
                        if any(h.kind!='REVIEW_CODE' for h in detector.find(v)):residual.append({'unit':'metadata','kind':'METADATA','rule':'metadata_residual'})
    return {'residual_count':len(residual),'residuals':residual,'blockers':sorted(blockers),'status':'CHECKED' if not residual and not blockers else 'NEEDS_REVIEW'}

def redact(workspace,password):
    ws=Path(workspace).resolve();vault=ws/'private'/'task.lpcv';job=open_vault(vault,password)
    if not job.get('reviewed'):raise ValueError('LOCAL_REVIEW_REQUIRED')
    if job['status'] not in ('REVIEWED','NEEDS_REVIEW','CHECKED'):raise ValueError('JOB_STATE_INVALID')
    detector=make_detector(job);rule_only=require_ner(detector)
    tok=Tokenizer(job['task']);results=[];pending=[]
    share=ws/'share'
    if share.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
    for fi,f in enumerate(job['files']):
        data=input_data(f);doc=Document(data,f['suffix']);_attach(doc,f)
        kept=collections.Counter();masked=[]
        for u in doc.units:
            for h in u.hits:
                value=u.text[h.start:h.end]
                if not h.mask:kept[h.kind,value]+=1
                else:masked.append(value)
        office_masks=f['suffix'] in ('.docx','.xlsx','.pptx');mask_slots=[];token_by_span={};mask_groups={}
        for u in doc.units:
            if u.kind=='ocr':continue
            offset=0
            selected=sorted((h for h in u.hits if h.mask),key=lambda item:item.start)
            expected_text=u.text
            for h in reversed(selected):expected_text=expected_text[:h.start]+'***'+expected_text[h.end:]
            if office_masks and selected:mask_groups[u.key]={'source_ref':u.source_ref,'expected_text':expected_text,'slots':[]}
            for h in sorted(u.hits,key=lambda item:item.start):
                if not h.mask:continue
                token=tok.token(u.text[h.start:h.end],h.kind,h.entity,f.get('case_id',fi) if job.get('groups_confirmed') else fi)
                token_by_span[(u.key,h.start,h.end)]=token
                if office_masks:
                    start=h.start+offset;mask_groups[u.key]['slots'].append({'start':start,'end':start+3,'token':token})
                    offset+=3-(h.end-h.start)
        def replace(u,h):
            token=token_by_span.get((u.key,h.start,h.end))
            if token is None:token=tok.token(u.text[h.start:h.end],h.kind,h.entity,f.get('case_id',fi) if job.get('groups_confirmed') else fi)
            return '***' if office_masks else token
        doc.manual_rectangles=f.get('rectangles',[])
        output=doc.output(replace)
        # A deliberately kept occurrence of the same literal is allowed only at reviewed count.
        known_masked=[v for v in masked if not any(k[1]==v for k in kept)]
        output_doc=Document(output,f['suffix'])
        ver=verify_data(output,f['suffix'],detector,kept,known_masked,output_doc)
        name=f'file-{fi+1:03d}{f["suffix"]}'
        if job.get('scenario'):
            from .organize import relative_name
            name=relative_name(f,fi)
        f['output_name']=name;f['output_sha256']=digest(output)
        if office_masks:
            output_units=[u for u in output_doc.units if u.kind!='ocr'];used=set()
            for group in mask_groups.values():
                candidates=[(i,u) for i,u in enumerate(output_units) if u.key not in used and u.text==group['expected_text']]
                same_ref=[item for item in candidates if item[1].source_ref==group['source_ref']]
                if same_ref:candidates=same_ref
                if not candidates:raise ValueError('MASK_SLOT_MISMATCH')
                _,matched=candidates[0];used.add(matched.key)
                same_ref_units=[u for u in output_units if u.source_ref==matched.source_ref]
                ordinal=next(i for i,u in enumerate(same_ref_units) if u.key==matched.key)
                for slot in group['slots']:
                    mask_slots.append({'unit_ref':matched.source_ref,'unit_ordinal':ordinal,'start':slot['start'],'end':slot['end'],'token':slot['token']})
            output_by_ref=collections.defaultdict(list)
            for u in output_units:output_by_ref[u.source_ref].append(u)
            if any(slot['unit_ref'] not in output_by_ref or slot['unit_ordinal']>=len(output_by_ref[slot['unit_ref']]) or output_by_ref[slot['unit_ref']][slot['unit_ordinal']].text[slot['start']:slot['end']]!='***' for slot in mask_slots):
                raise ValueError('MASK_SLOT_MISMATCH')
            f['mask_slots']=mask_slots
        f['token_counts']=dict(collections.Counter(TOKEN.findall('\n'.join(u.text for u in output_doc.units))))
        f['masked_values']=known_masked
        f['kept']=[[k[0],k[1],v] for k,v in kept.items()]
        f['media_restore']={}
        if f['suffix'] in ('.docx','.xlsx','.pptx'):
            with zipfile.ZipFile(io.BytesIO(data)) as orig,zipfile.ZipFile(io.BytesIO(output)) as red:
                for n in orig.namelist():
                    if n.lower().endswith(('.png','.jpg','.jpeg')) and not n.lower().startswith('docprops/'):
                        f['media_restore'][n]={'redacted_hash':digest(red.read(n)),'original':b64(orig.read(n))}
        pending.append((name,output));results.append({'index':fi,**ver})
        if job.get('scenario',{}).get('export_md'):
            from .exporter import markdown,verify_markdown
            md=markdown(doc,replace,fi)
            md_ver=verify_markdown(md,detector,kept,known_masked)
            results.append({'index':fi,'derived':'markdown',**md_ver})
            pending.append((name+'.md',md))
        if job.get('scenario',{}).get('ppt_pdf') and f['suffix']=='.pptx':
            from .exporter import ppt_pdf
            pdf=ppt_pdf(output)
            pv=verify_data(pdf,'.pdf',detector,kept,known_masked)
            results.append({'index':fi,'derived':'pdf',**pv});pending.append((name+'.pdf',pdf))
    share.mkdir(mode=0o700)
    for name,data in pending:
        (share/name).parent.mkdir(parents=True,exist_ok=True,mode=0o700);atomic(share/name,data)
    job['derived_outputs']=[{'name':name,'sha256':digest(data)} for name,data in pending if name not in {f['output_name'] for f in job['files']}]
    if job.get('scenario',{}).get('export_md'):
        from .exporter import index_files
        for name,data in index_files(job,pending).items():
            iv=verify_data(data,'.md',detector,ignore_optional_codes=True)
            results.append({'derived':'index',**iv})
            atomic(share/name,data);job['derived_outputs'].append({'name':name,'sha256':digest(data)})
    job['mapping']=tok.mapping;job['verification']=results
    job['status']='CHECKED' if all(v['status']=='CHECKED' for v in results) else 'NEEDS_REVIEW'
    seal(vault,job,password)
    report=stats(job);report['ner']=not rule_only;report['verification']=results;report['outputs']=[{'name':f['output_name'],'sha256':f['output_sha256']} for f in job['files']]
    report['created_at']=job['created_at'];report['reviewed_at']=job['reviewed_at'];report['exported_at']=now()
    report['actions']=[{'file_index':fi,'unit':u['key'],'start':h['start'],'end':h['end'],'kind':h['kind'],'recognizer':h['rule'],'source_score':h['confidence'],'action':'mask' if h['mask'] else 'authorized_keep','reviewer':'local-user','policy_version':POLICY_VERSION} for fi,f in enumerate(job['files']) for u in f['units'] for h in u['hits']]
    report['manual_rectangles']=[{'file_index':fi,'count':len(f.get('rectangles',[]))} for fi,f in enumerate(job['files']) if f.get('rectangles')]
    report['meaning']='机械检查通过不等于法律匿名化认证；未经许可不自动外发。'
    publish(ws/'audit-report.json',report)
    publish(share/'audit-report.json',report)
    return report

def verify(workspace,password):
    ws=Path(workspace).resolve();job=open_vault(ws/'private'/'task.lpcv',password);detector=make_detector(job);require_ner(detector)
    results=[]
    for i,f in enumerate(job['files']):
        data=(ws/'share'/f['output_name']).read_bytes()
        r=verify_data(data,f['suffix'],detector,{(k,v):n for k,v,n in f['kept']},f['masked_values'])
        if digest(data)!=f['output_sha256']:r['status']='NEEDS_REVIEW';r['blockers'].append('OUTPUT_CHANGED_REVIEW_REQUIRED')
        results.append({'index':i,**r})
    for prior in job.get('verification',[]):
        if prior.get('derived') and prior['status']!='CHECKED':results.append(prior)
    for f in job.get('derived_outputs',[]):
        p=ws/'share'/f['name']
        if not p.exists() or digest(p.read_bytes())!=f['sha256']:results.append({'derived':True,'status':'NEEDS_REVIEW','blockers':['DERIVED_OUTPUT_CHANGED']})
    report={'task':job['task'],'status':'CHECKED' if all(r['status']=='CHECKED' for r in results) else 'NEEDS_REVIEW','files':results}
    publish(ws/'verify-report.json',report);return report

def restore(workspace,password,output,edited=None,index=0):
    ws=Path(workspace).resolve();job=open_vault(ws/'private'/'task.lpcv',password)
    if index<0 or index>=len(job['files']):raise ValueError('FILE_INDEX_INVALID')
    f=job['files'][index];out=Path(output).resolve()
    if out.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
    if str(out) in {x['source'] for x in job['files']}:raise ValueError('SOURCE_OVERWRITE_FORBIDDEN')
    if out.suffix.lower()!=f['suffix']:raise ValueError('OUTPUT_EXTENSION_MISMATCH')
    conflicts=[]
    if not edited:
        raw=unb64(f['original'])
        if digest(raw)!=f['sha256']:raise ValueError('ARCHIVE_INTEGRITY_FAILED')
        atomic(out,raw)
        report={'task':job['task'],'status':'RESTORED_ORIGINAL','index':index,'sha256':digest(raw),'conflicts':[]}
    else:
        if f['suffix'] not in ('.docx','.xlsx','.pptx','.txt','.md','.csv','.tsv','.eml','.json','.xml','.log'):raise ValueError('EDITED_RESTORE_UNSUPPORTED')
        data=Path(edited).read_bytes();doc=Document(data,f['suffix'])
        blockers=set(doc.issues)-SOFT_ISSUES
        if blockers:raise ValueError('EDITED_DOCUMENT_UNSUPPORTED')
        text='\n'.join(u.text for u in doc.units if u.kind!='ocr')
        if f['suffix'] in ('.docx','.xlsx','.pptx') and f.get('mask_slots') is not None:
            units_by_ref=collections.defaultdict(list)
            for u in doc.units:
                if u.kind!='ocr':units_by_ref[u.source_ref].append(u)
            by_locator=collections.defaultdict(list)
            for slot in f['mask_slots']:by_locator[(slot['unit_ref'],slot['unit_ordinal'])].append(slot)
            unit_locators={}
            for ref,units in units_by_ref.items():
                for ordinal,unit in enumerate(units):unit_locators[(ref,ordinal)]=unit
            for locator,unit in unit_locators.items():
                slots=by_locator.get(locator,[])
                if unit.text.count('***')!=len(slots):conflicts.append({'code':'STAR_MASK_COUNT_CHANGED'})
            for locator,slots in by_locator.items():
                unit=unit_locators.get(locator)
                if unit is None:
                    conflicts.append({'code':'STAR_MASK_UNIT_CHANGED'});continue
                for slot in slots:
                    if slot['token'] not in job['mapping'] or unit.text[slot['start']:slot['end']]!='***':
                        conflicts.append({'code':'STAR_MASK_POSITION_CHANGED'});continue
                    unit.hits.append(Hit(slot['start'],slot['end'],'SECRET','restore',entity=slot['token']))
                unit.hits.sort(key=lambda h:h.start)
        else:
            counts=collections.Counter(TOKEN.findall(text));expected=f.get('token_counts',{})
            for token,num in expected.items():
                if counts[token]!=num:conflicts.append({'code':'TOKEN_COUNT_CHANGED','expected':num,'actual':counts[token]})
            for token in counts:
                if token not in expected or token not in job['mapping']:conflicts.append({'code':'UNKNOWN_OR_COPIED_TOKEN'})
            scrub=TOKEN.sub('',text)
            if re.search(r'\[P:|P:'+re.escape(job['task']),scrub):conflicts.append({'code':'DAMAGED_TOKEN'})
        if conflicts:
            report={'task':job['task'],'status':'NEEDS_REVIEW','index':index,'conflicts':conflicts}
        else:
            # Exact tokens only; never infer missing text or normalize a damaged placeholder.
            if not (f['suffix'] in ('.docx','.xlsx','.pptx') and f.get('mask_slots') is not None):
                for u in doc.units:
                    if u.kind=='ocr':continue
                    u.hits=[Hit(m.start(),m.end(),'SECRET','restore') for m in TOKEN.finditer(u.text)]
            raw=doc.output(lambda u,h:job['mapping'][h.entity] if h.rule=='restore' and h.entity else job['mapping'][u.text[h.start:h.end]])
            if f['suffix'] in ('.docx','.xlsx','.pptx'):
                b=io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(data)) as incoming,zipfile.ZipFile(io.BytesIO(raw)) as z,zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as dest:
                    for name in z.namelist():
                        payload=z.read(name)
                        if name in f.get('media_restore',{}):
                            record=f['media_restore'][name]
                            if name not in incoming.namelist() or digest(incoming.read(name))!=record['redacted_hash']:
                                conflicts.append({'code':'IMAGE_CHANGED_REVIEW_REQUIRED'})
                            else:payload=unb64(record['original'])
                        dest.writestr(name,payload)
                raw=b.getvalue()
            if conflicts:report={'task':job['task'],'status':'NEEDS_REVIEW','index':index,'conflicts':conflicts}
            else:
                atomic(out,raw);report={'task':job['task'],'status':'RESTORED_EDITED','index':index,'conflicts':[]}
    # No plaintext restoration preview or raw path goes into the report.
    publish(out.parent/(out.stem+'.restore-report.json'),report)
    job.setdefault('restore_events',[]).append({'index':index,'status':report['status'],'time':now(),'actor':'local-user','sequence':len(job.get('restore_events',[]))+1})
    seal(ws/'private'/'task.lpcv',job,password)
    return report
