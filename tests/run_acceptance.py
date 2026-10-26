"""End-to-end acceptance with synthetic documents only. Never point this at real files."""
import io,json,sys,hashlib,zipfile
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parent)]
from fixtures import make_all,DICT,PERSON,PHONE
from cloak.vault import open_vault,seal
from cloak.workflow import scan,review_update,redact,verify,restore,SOFT_ISSUES
from cloak.formats import Document

root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=True)
paths=make_all(root/'originals',with_image=True)
pw='SYNTHETIC-ACCEPTANCE-only-2026'
ws=root/'task'
scan(paths,ws,pw,dictionary=DICT)
job=open_vault(ws/'private/task.lpcv',pw)
review_update(job,confirmations=sorted(set(i for f in job['files'] for i in f['issues'])&SOFT_ISSUES))
seal(ws/'private/task.lpcv',job,pw)
r=redact(ws,pw);v=verify(ws,pw);assert r['status']=='CHECKED',r;assert v['status']=='CHECKED',v
restores=[]
for i,p in enumerate(paths):
 out=root/'restored'/('original-'+str(i)+p.suffix)
 rr=restore(ws,pw,out,index=i);assert out.read_bytes()==p.read_bytes()
 d=Document((ws/'share'/f'file-{i+1:03d}{p.suffix}').read_bytes(),p.suffix)
 text='\n'.join(u.text for u in d.units)
 assert PERSON not in text and PHONE not in text
 restores.append({'format':p.suffix,'original_sha256_match':True,'output_sha256':hashlib.sha256((ws/'share'/f'file-{i+1:03d}{p.suffix}').read_bytes()).hexdigest()})
 if p.suffix in ('.docx','.xlsx','.pptx','.txt','.md'):
  out=root/'restored'/('edited-'+str(i)+p.suffix)
  rr=restore(ws,pw,out,ws/'share'/f'file-{i+1:03d}{p.suffix}',i);assert rr['status']=='RESTORED_EDITED',rr
report={'synthetic_only':True,'file_count':len(paths),'status':v['status'],'formats':restores,'masked_by_category':r['masked_candidates']}
(root/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
