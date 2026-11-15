from pathlib import Path
import re
import yaml

# New env keys an honest migration may add; anything else (npm/docker/shell switches) changes what the commands do.
SAFE_ENV={'CI','FORCE_COLOR','NO_COLOR','TERM','TZ','LANG','LC_ALL','PYTHONUNBUFFERED','PYTHONIOENCODING'}

def closure(graph):
    out={}
    def visit(node, trail):
        if node in trail or node not in graph: raise ValueError('invalid dependency graph')
        if node not in out:
            values=set(graph[node])
            for dep in graph[node]: values |= visit(dep,trail|{node})
            out[node]=values
        return out[node]
    for node in graph: visit(node,set())
    return out

def preserved_variable(original, actual):
    if actual == original:
        return True
    if not isinstance(original, str) or not isinstance(actual, str):
        return False
    reference = re.fullmatch(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', original)
    return bool(reference and re.fullmatch(r'\$\{\{\s*secrets\.' + re.escape(reference[1]) + r'\s*\}\}', actual))

def ci_contract(ws,secrets):
    task,built=baseline()
    try:
        old=yaml.safe_load(built['.gitlab-ci.yml'])
        names=set(old)-{'stages','variables'}
        graph={n:old[n].get('needs',[]) for n in names}
        target={}; workflows=list((ws/'.github/workflows').glob('*.y*ml'))
        if not workflows: return False,'workflow missing'
        for path in workflows:
            flow=yaml.safe_load(path.read_text())
            trigger=flow.get('on',flow.get(True))
            push=(trigger=='push' or isinstance(trigger,list) and 'push' in trigger or
                  isinstance(trigger,dict) and 'push' in trigger and trigger['push'] in (None,{}))
            if not push: return False,'unfiltered push trigger missing'
            jobs=flow['jobs']; global_env=flow.get('env',{})
            if len(workflows)!=1: return False,'dependent jobs must share one workflow'
            for name,job in jobs.items():
                if name in target: return False,'duplicate job'
                if any(job.get(k) for k in ('container','services','strategy','uses')): return False,'unsupported execution context'
                needs=job.get('needs',[])
                if isinstance(needs,str): needs=[needs]
                steps=job['steps']
                commands=[]; checked_out=False
                defaults={**flow.get('defaults',{}).get('run',{}),**job.get('defaults',{}).get('run',{})}
                env={**global_env,**job.get('env',{})}
                for step in steps:
                    if step.get('if') not in (None,True,'success()','${{ success() }}'): return False,'step execution changed'
                    if step.get('continue-on-error',False): return False,'step failure propagation changed'
                    if 'run' in step:
                        effective={**env,**step.get('env',{})}
                        if not checked_out: return False,'shell step runs before repository checkout'
                        if set(effective)-set(old['variables'])-SAFE_ENV: return False,'execution environment overridden'
                        if any(not preserved_variable(v,effective.get(k)) for k,v in old['variables'].items()): return False,'effective variables not preserved'
                        settings={**defaults,**step}
                        if settings.get('shell','bash') not in ('bash','sh'): return False,'unsupported shell'
                        if settings.get('working-directory','.') not in ('.','./'): return False,'working directory changed'
                        commands += step['run'].strip().splitlines()
                    elif step.get('uses','').startswith('actions/checkout@'):
                        options=step.get('with') or {}
                        if not isinstance(options,dict) or str(options.get('path','.')).strip() not in ('','.','./') or 'repository' in options: return False,'checkout is not the repository root'
                        checked_out=True
                    else: return False,'unsupported replacement for shell job'
                env={**global_env,**job.get('env',{})}
                if name not in names or commands!=old[name]['script']: return False,'job commands changed'
                if job.get('if') not in (None,True,'success()','${{ success() }}'): return False,'conditional changes graph'
                if job.get('continue-on-error',False): return False,'failure propagation changed'
                if job.get('runs-on') not in ('ubuntu-latest',['ubuntu-latest']): return False,'runner changed'
                target[name]=needs
        if set(target)!=names or closure(target)!=closure(graph): return False,'job dependency graph changed'
        return True,'YAML jobs, transitive dependencies, shell commands and variables preserved'
    except (OSError,ValueError,TypeError,KeyError,AttributeError,yaml.YAMLError):
        return False,'invalid workflow or graph'

from pathlib import Path
import m2_tasks as mt

def baseline():
    task=mt.load_task(Path(__file__).resolve().parent)
    folder=task.dir/'workspace'
    built={p.relative_to(folder).as_posix():task.fill(p.read_text()) for p in folder.rglob('*') if p.is_file()}
    return task,built
