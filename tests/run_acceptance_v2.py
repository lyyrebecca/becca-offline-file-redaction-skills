"""Synthetic, unattended verification only; real materials always require human review."""
import sys,time,json,hashlib,zipfile,io,platform,subprocess
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parent)]
from fixtures import make_all,DICT
from cloak.workflow import scan,redact,review_update,verify,restore,SOFT_ISSUES
from cloak.organize import set_assignments
from cloak.vault import open_vault,seal
from cloak.formats import Document
PW='SYNTHETIC-acceptance-v2-2026'
root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=False);files=make_all(root/'input')
records={}
import socket
try:
    connection=socket.socket();connection.settimeout(2);connection.connect(('1.1.1.1',443))
except PermissionError:pass
else:raise AssertionError('OS_NETWORK_DENIAL_NOT_ACTIVE')
finally:connection.close()
def run(name,scenario):
    ws=root/name;t=time.perf_counter();scan(list(reversed(files)),ws,PW,dictionary=DICT,scenario=scenario);scan_secs=time.perf_counter()-t
    j=open_vault(ws/'private/task.lpcv',PW);unit_count=sum(len(f['units']) for f in j['files'])
    set_assignments(j,[{'index':i,'case_id':'CASE001'} for i in range(len(j['files']))]);review_update(j,confirmations=list(SOFT_ISSUES));seal(ws/'private/task.lpcv',j,PW)
    t=time.perf_counter();r=redact(ws,PW);export_secs=time.perf_counter()-t
    v=verify(ws,PW);assert r['status']==v['status']=='CHECKED',(r['verification'],v)
    restored=[]
    for i,f in enumerate(j['files']):
        output=root/f'{name}-restored-{i}{f["suffix"]}';rr=restore(ws,PW,output,index=i);assert output.read_bytes()==Path(f['source']).read_bytes();restored.append(rr['status'])
    records[name]={'file_count':len(files),'scan_seconds':round(scan_secs,3),'export_seconds':round(export_secs,3),'units_persisted':unit_count,'status':r['status'],'verification':v['status'],'restored_byte_identical':len(restored),'derived_count':len(open_vault(ws/'private/task.lpcv',PW).get('derived_outputs',[]))}
run('cold',{'purpose':'ai','organization':'single'})
run('warm',{'purpose':'ai','organization':'single'})
(root/'core-acceptance.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
# Independent student distribution + extra PDF path.
p=next(p for p in files if p.suffix=='.pptx');ws=root/'teaching';t=time.perf_counter();scan([p],ws,PW,dictionary=DICT,scenario={'purpose':'students','organization':'single','ppt_pdf':True});j=open_vault(ws/'private/task.lpcv',PW);set_assignments(j,[{'index':0,'case_id':'CASE001'}]);review_update(j,confirmations=list(SOFT_ISSUES));seal(ws/'private/task.lpcv',j,PW);r=redact(ws,PW);v=verify(ws,PW);assert r['status']==v['status']=='CHECKED',(r['verification'],v)
from pptx import Presentation
out=next((ws/'share').rglob('*.pptx'));assert len(Presentation(out).slides)==1
from pypdf import PdfReader
pdf=next((ws/'share').rglob('*.pdf'));reader=PdfReader(pdf);assert len(reader.pages)==1 and not reader.pages[0].extract_text()
records['teaching']={'seconds':round(time.perf_counter()-t,3),'status':r['status'],'hidden_slides_removed':j['files'][0]['teaching']['hidden_slides_removed'],'pdf_pages':len(reader.pages),'pdf_text_layer':False}
records['machine']={'platform':platform.platform(),'processor':platform.machine(),'network':'OS sandbox deny network*; allow Unix IPC only; IP connect denied verified','external_llm_calls':0,'test_data':'synthetic only'}
(root/'acceptance.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));print(json.dumps(records,ensure_ascii=False,indent=2))
