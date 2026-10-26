"""Student copy: remove private PPT parts and perform package-graph garbage collection."""
import io,posixpath,re,zipfile
from pathlib import PurePosixPath
from lxml import etree as E
from .formats import PARSER,MAX_EXPANDED
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PR='http://schemas.openxmlformats.org/package/2006/relationships'

def rel_path(part):
    return (posixpath.dirname(part)+'/_rels/'+posixpath.basename(part)+'.rels').lstrip('/') if part else '_rels/.rels'
def resolve(part,target):
    if target.startswith('/'):return target[1:]
    return posixpath.normpath(posixpath.join(posixpath.dirname(part),target))

def student_copy(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(x.file_size for x in z.infolist())>MAX_EXPANDED:raise ValueError('PACKAGE_LIMIT')
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('PACKAGE_DUPLICATE')
        if any(x.flag_bits&1 or x.filename.startswith('/') or '..' in PurePosixPath(x.filename).parts for x in z.infolist()):raise ValueError('PACKAGE_INVALID')
        parts={n:z.read(n) for n in z.namelist()}
    if 'ppt/presentation.xml' not in parts:raise ValueError('PACKAGE_TYPE_MISMATCH')
    roots={}
    for name,raw in parts.items():
        if name.endswith(('.xml','.rels')):
            root=E.fromstring(raw,PARSER)
            if root.getroottree().docinfo.doctype:raise ValueError('XML_DTD_FORBIDDEN')
            roots[name]=root
    hidden={n for n,r in roots.items() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n) and r.get('show') in ('0','false')}
    removed_rels=0
    for name,root in roots.items():
        if not name.endswith('.rels'):continue
        part='' if name=='_rels/.rels' else name.replace('/_rels/','/')[:-5]
        removed_ids=set()
        for rel in list(root):
            kind=rel.get('Type','').split('/')[-1]
            dest=resolve(part,rel.get('Target',''))
            if kind in ('notesSlide','notesMaster','comments','commentAuthors','person','people') or any(term in kind.lower() for term in ('comment','person','people')) or dest in hidden:
                removed_ids.add(rel.get('Id'));root.remove(rel);removed_rels+=1
        if part in roots and removed_ids:
            for node in list(roots[part].iter()):
                for attr,val in list(node.attrib.items()):
                    if E.QName(attr).namespace==R and val in removed_ids:
                        if E.QName(node).localname in ('sldId','hlinkClick','hlinkHover') and node.getparent() is not None:node.getparent().remove(node);break
                        else:del node.attrib[attr]
    presentation=roots['ppt/presentation.xml']
    for node in list(presentation):
        if E.QName(node).localname in ('custShowLst','notesMasterIdLst'):presentation.remove(node)
    # Only parts reachable from package root survive. Notes images and hidden slide media
    # must not remain as recoverable orphan ZIP entries.
    reachable={'[Content_Types].xml','_rels/.rels'};queue=[''];visited=set()
    while queue:
        part=queue.pop()
        if part in visited:continue
        visited.add(part);rp=rel_path(part)
        if rp in roots:
            reachable.add(rp)
            for rel in roots[rp]:
                if rel.get('TargetMode')=='External':continue
                dest=resolve(part,rel.get('Target',''))
                if dest in parts and dest not in reachable:reachable.add(dest);queue.append(dest)
    ct=roots['[Content_Types].xml']
    for node in list(ct):
        if node.get('PartName') and node.get('PartName').lstrip('/') not in reachable:ct.remove(node)
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(reachable):
            if name in parts:z.writestr(name,E.tostring(roots[name],encoding='UTF-8',xml_declaration=True) if name in roots else parts[name])
    return b.getvalue(),{'hidden_slides_removed':len(hidden),'private_relationships_removed':removed_rels,'orphan_parts_removed':len(set(parts)-reachable)}
