"""Reproducible coverage census. Reads templates/metadata, never starts Claude.

Legacy projects are classified by their primary task, since core/gen predate that field.
Formats are multi-label; workspace extensions plus declared non-file formats are counted.
Session turns are observations from real runs, never inferred from file counts.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import m2_tasks as mt

CORE_PROJECTS = {
    'infra': {'t05','t24','t25'}, 'cli': {'t07','t16','t17'}, 'ci-cd': {'t08','t14','t22'}}
SUFFIXES = {'.env':'dotenv','.yaml':'yaml','.yml':'yaml','.json':'json','.toml':'toml',
    '.ini':'ini','.properties':'properties','.xml':'xml','.py':'python','.js':'javascript',
    '.ts':'typescript','.go':'go','.java':'java','.sql':'sql','.sh':'shell','.md':'markdown',
    '.log':'log','.tf':'terraform','.ipynb':'ipynb','.kts':'gradle','.csv':'csv','.har':'har'}


def project(task):
    if task.meta.get('project'): return task.meta['project']
    short=task.id.split('-')[0]
    if task.suite=='core':
        return next((p for p,ids in CORE_PROJECTS.items() if short in ids),'backend')
    n=int(short[1:])
    if n<=7:return 'data'
    if n in (21,22):return 'frontend'
    if n in (23,24):return 'infra'
    if n==26:return 'cli'
    if n in (27,28):return 'ci-cd'
    return 'backend'


def format_labels(meta,files):
    found={'dotenv' if x=='env' else x for x in meta.get('formats',[])}
    for rel,text in files.items():
        path=Path(rel)
        if path.suffix in SUFFIXES:found.add(SUFFIXES[path.suffix])
        if path.name.startswith('.env'):found.add('dotenv')
        if path.name=='Dockerfile':found.add('dockerfile')
        if path.name in ('compose.yaml','docker-compose.yml'):found.add('compose')
        if 'k8s' in path.parts and path.suffix in ('.yaml','.yml'):found.add('k8s')
        if 'HTTP/1.' in text:found.add('http')
        if 'Traceback (most recent call last)' in text:found.add('stacktrace')
    return sorted(found)


def formats(task):
    files={}
    for path in (task.dir/'workspace').rglob('*'):
        if path.is_file():
            try:files[path.relative_to(task.dir/'workspace').as_posix()]=path.read_text()
            except UnicodeDecodeError:continue
    return format_labels(task.meta,files)


def census(tasks):
    counts={field:Counter() for field in ('category','language','project','secret_requirement','length','channels','formats','secret_kinds','negative_kinds')}
    files=[];multi=0;repeated=0;derived=0
    for t in tasks:
        meta=t.meta
        counts['category'][t.category]+=1
        counts['language'][meta.get('language','ko')]+=1
        counts['project'][project(t)]+=1
        counts['secret_requirement'][meta.get('secret_requirement',t.category if t.category in {'property','use','transport','identity'} else 'none')]+=1
        counts['length'][meta.get('length','short')]+=1
        channels=meta.get('channels',['file']);counts['channels'].update(channels);multi+=len(channels)>1
        counts['formats'].update(formats(t))
        counts['secret_kinds'].update({s['kind'] for s in t.spec.get('secrets',{}).values() if 'kind' in s})
        if meta.get('negative_kind'):counts['negative_kinds'][meta['negative_kind']]+=1
        derived+=any('from' in s for s in t.spec.get('secrets',{}).values())
        texts=[]
        for path in (t.dir/'workspace').rglob('*'):
            if path.is_file():
                try:texts.append(path.read_text())
                except UnicodeDecodeError:pass
        sources=texts+mt.strings({k:v for k,v in t.spec.items() if k in {'prompt','session_env','append_system_prompt','mcp_fixture','history','worktree_changes','final_commit','setup'}})
        refs=Counter(m.group(2) for text in sources for m in mt.SECRET_REF.finditer(text) if m.group(1)=='secret')
        repeated+=any(n>1 for n in refs.values())
        files.append(sum(1 for p in (t.dir/'workspace').rglob('*') if p.is_file()))
    return {'tasks':len(tasks),'needs_secret_value':sum(t.spec['needs_secret_value'] for t in tasks),
        'multi_channel':multi,'with_derived_forms':derived,'with_repeated_secret':repeated,
        'workspace_files':{'min':min(files,default=0),'max':max(files,default=0)},
        **{k:dict(sorted(v.items())) for k,v in counts.items()}}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tasks',nargs='*',default=['all']);p.add_argument('--json',action='store_true');a=p.parse_args()
    tasks=mt.load_tasks(a.tasks)
    groups={suite:census([t for t in tasks if t.suite==suite]) for suite in sorted({t.suite for t in tasks})}
    groups['combined']=census(tasks)
    print(json.dumps(groups,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
