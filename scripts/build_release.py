#!/usr/bin/env python3
"""Build a source-only Skill ZIP; never include task vaults or working outputs."""
from pathlib import Path
import hashlib,json,zipfile,argparse
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'.git','.venv','__pycache__','.pytest_cache','dist','build','private','share','restored'}
def selected(root):
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink():continue
        rel=p.relative_to(root)
        if any(part in EXCLUDE or part.endswith('.app') or part.startswith('validation') for part in rel.parts):continue
        if p.name=='.DS_Store' or p.suffix in ('.pyc','.lpcv','.log') or p.name=='.env' or p.name.startswith('.env.'):continue
        yield p

def build(destination):
    brand=json.loads((ROOT/'assets/brand.json').read_text('utf-8'));version=brand['version'];destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    files=list(selected(ROOT));dest=destination/f'becca-offline-file-redaction-skills-v{version}.zip'
    if any(p.is_relative_to(destination) for p in files):raise ValueError('BUILD_DESTINATION_MUST_BE_EXCLUDED_OR_OUTSIDE_PROJECT')
    manifest={'name':brand['name'],'version':version,'archive_root':'legal-privacy-cloak','files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:
            rel=Path('legal-privacy-cloak')/p.relative_to(ROOT);info=zipfile.ZipInfo(str(rel),(2026,10,26,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(0o100755 if p.stat().st_mode&0o111 else 0o100644)<<16;z.writestr(info,p.read_bytes())
    with zipfile.ZipFile(dest) as z:
        if z.testzip():raise ValueError('ARCHIVE_INTEGRITY_FAILED')
    manifest['archive_sha256']=hashlib.sha256(dest.read_bytes()).hexdigest()
    (destination/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (destination/'SHA256SUMS.txt').write_text(manifest['archive_sha256']+'  '+dest.name+'\n',encoding='utf-8')
    print(json.dumps({'status':'BUILT','version':version,'file_count':len(files),'bytes':dest.stat().st_size,'sha256':manifest['archive_sha256']},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'dist');a=p.parse_args();build(a.output)
