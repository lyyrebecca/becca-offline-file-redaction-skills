#!/usr/bin/env python3
"""CI diagnostics for generated synthetic raster data only; never accepts user files."""
import argparse,sys,subprocess,json,hashlib,time,platform
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cloak.platforms import prepare_tools
prepare_tools()
from fixtures import image,fixture_font
from PIL import Image,ImageFont
import io
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
raw=image();file=a.output/'synthetic-raster.png';file.write_bytes(raw);im=Image.open(io.BytesIO(raw)).convert('L');font=fixture_font()
record={'synthetic_only':True,'platform':platform.platform(),'python':platform.python_version(),'image_sha256':hashlib.sha256(raw).hexdigest(),'image_extrema':im.getextrema(),'black_pixels':sum(v<128 for v in im.getdata()),'font_name':font.getname(),'font_bbox':font.getbbox('Phone: 13812345678'),'ocr':{}}
for lang in ('chi_sim+eng','eng'):
    start=time.perf_counter();result=subprocess.run(['tesseract',str(file),'stdout','-l',lang,'--psm','11','-c','tessedit_create_tsv=1'],capture_output=True,timeout=60)
    (a.output/(lang+'.tsv')).write_bytes(result.stdout)
    record['ocr'][lang]={'seconds':round(time.perf_counter()-start,3),'returncode':result.returncode,'stdout_head_repr':repr(result.stdout[:1000]),'stderr':result.stderr.decode('utf-8','replace')[:1000]}
record['version']=subprocess.run(['tesseract','--version'],capture_output=True,text=True).stdout.splitlines()[:3]
(a.output/'diagnostics.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=False,indent=2))
