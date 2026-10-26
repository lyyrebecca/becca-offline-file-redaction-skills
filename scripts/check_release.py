#!/usr/bin/env python3
"""Non-content structure and parity check; never opens user case files."""
from pathlib import Path
import ast,json,re,hashlib
root=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(root/'scripts'))
from build_release import selected
errors=[]
for p in (root/'scripts').rglob('*.py'):
    try:ast.parse(p.read_text('utf-8'))
    except SyntaxError:errors.append('SYNTAX:'+str(p.relative_to(root)))
for p in root.rglob('*.md'):
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text('utf-8')):
        if '://' not in target and not target.startswith(('#','mailto:')) and not (p.parent/target.split('#')[0]).exists():errors.append('MISSING_LINK:'+str(p.relative_to(root))+':'+target)
for n in ['README.md','README.en.md','LICENSE','THIRD_PARTY_NOTICES.md','docs/INSTALL.md','docs/VERIFICATION.md','docs/FAQ.md','docs/evidence/ui-acceptance.json','SKILL.md','agents/openai.yaml','assets/brand-icon.jpg','assets/ui-reference.png','assets/ui/index.html','assets/ui/app.js','assets/ui/app.css','开始使用.md']:
    if not (root/n).is_file():errors.append('MISSING:'+n)
for n in ['scripts/run.sh','信息隐身衣.command']:
    if not (root/n).stat().st_mode&0o111:errors.append('NOT_EXECUTABLE:'+n)
brand=json.loads((root/'assets/brand.json').read_text());assert brand['email']=='1849883220@qq.com'
if brand['email'] not in (root/'assets/ui/index.html').read_text():errors.append('BRAND_EMAIL_MISSING')
for p in selected(root):
    rel=str(p.relative_to(root))
    if p.suffix.lower() in ('.md','.txt','.json','.py','.sh','.yaml','.yml','.html','.js','.css'):
        content=p.read_text('utf-8')
        # Avoid publishing machine-specific paths or real access-token literals.
        bad_paths=('/'+'Users/', '/'+'var/'+'folders/', '/'+'private/'+'var/'+'folders/')
        if any(value in content for value in bad_paths):errors.append('PERSONAL_PATH:'+rel)
        if re.search(r'(?:gh'+'p_|gh'+'o_|github_'+'pat_)[A-Za-z0-9_]{20,}',content):errors.append('CREDENTIAL_PATTERN:'+rel)
for p in root.rglob('*.lpcv'):
    if '.git' not in p.parts:errors.append('VAULT_IN_PROJECT')
print(json.dumps({'status':'PASS' if not errors else 'FAIL','version':brand['version'],'python_files':len(list((root/'scripts').rglob('*.py'))),'errors':errors},ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
