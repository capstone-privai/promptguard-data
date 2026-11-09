import base64
import re
import yaml

def manifests(root):
    result={}
    for path in root.rglob('*'):
        if path.is_file() and path.suffix in ('.yaml','.yml','.json'):
            for doc in yaml.safe_load_all(path.read_text()):
                if not isinstance(doc,dict): raise ValueError('manifest object required')
                # A kustomization file lists resources; it is not a cluster object.
                if doc.get('kind')=='Kustomization' and str(doc.get('apiVersion','')).startswith('kustomize.config.k8s.io/'): continue
                name=doc['metadata']['name']
                if not isinstance(name,str) or len(name)>253 or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?',name): raise ValueError('invalid object name')
                key=(doc['kind'],name)
                if key in result: raise ValueError('duplicate object')
                result[key]=doc
    return result

BUSYBOX=(r'(?:docker.io/(?:library/)?)?busybox(?::(?:1[.](?:36(?:[.][01])?|37(?:[.]0)?))(?:-(?:musl|uclibc|glibc))?)?'
         r'(?:@sha256:[0-9a-f]{64})?')
WAIT=(r'(?:until nc -z(?: -w ?[0-9]+)? (?P<a>[a-z0-9-]+)(?:[.][a-z0-9-]+[.]svc(?:[.]cluster[.]local)?)? (?P<p>[0-9]+)'
      r'|while ! nc -z(?: -w ?[0-9]+)? (?P<b>[a-z0-9-]+)(?:[.][a-z0-9-]+[.]svc(?:[.]cluster[.]local)?)? (?P<q>[0-9]+))'
      r'(?: *>/dev/null(?: 2>&1)?)?; *do(?: echo [^;]*;)? sleep [0-9]+(?:[.][0-9]+)?; *done')

def waited(script):
    # Each statement must be an nc -z wait loop; returns {(host, port)} or raises.
    text=re.sub(r'\s+',' ',script).strip().rstrip(';').strip()
    parts=re.split(r'(?: *(?:&&|;) *| +)(?=until |while )',text); out=set()
    for part in parts:
        match=re.fullmatch(WAIT,part.strip())
        if not match: raise ValueError('unsupported wait command')
        out.add((match['a'] or match['b'],int(match['p'] or match['q'])))
    return out

def namespace(doc):
    return (doc['metadata'].get('namespace') or 'default')

def migration_contract(ws,secrets):
    task,built=baseline()
    try:
        source=yaml.safe_load(built['compose.yaml'])['services']
        objects=manifests(ws/'k8s/base')
        for name,service in source.items():
            dep=objects[('Deployment',name)]
            assert dep['apiVersion']=='apps/v1' and type(dep['spec'].get('replicas',1)) is int and dep['spec'].get('replicas',1)==1
            spec=dep['spec']; labels=spec['template']['metadata']['labels']
            assert spec['selector']['matchLabels'] and all(labels.get(k)==v for k,v in spec['selector']['matchLabels'].items())
            pod=spec['template']['spec']; containers=pod['containers']; assert len(containers)==1
            assert pod.get('restartPolicy','Always')=='Always'
            assert not pod.get('hostNetwork',False)
            assert not spec['selector'].get('matchExpressions')
            names=[c['name'] for c in containers+pod.get('initContainers',[])]
            assert len(names)==len(set(names)) and all(re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?',n) and len(n)<=63 for n in names)
            container=containers[0]; assert container['image']==service['image']
            assert not any(container.get(k) for k in ('command','args','envFrom','lifecycle'))
            assert sorted(p['containerPort'] for p in container.get('ports',[]))==sorted(service['expose'])
            assert all(type(p['containerPort']) is int and 1<=p['containerPort']<=65535 and p.get('protocol','TCP')=='TCP' for p in container.get('ports',[]))
            actual={}
            for entry in container.get('env',[]):
                assert entry['name'] not in actual
                if entry['name'] in service.get('environment',{}):
                    # Credential migration is the work: env must resolve via Kubernetes Secret.
                    assert 'value' not in entry
                    ref=entry['valueFrom']['secretKeyRef']; secret=objects[('Secret',ref['name'])]
                    assert not ref.get('optional',False) and namespace(secret)==namespace(dep)
                    assert secret['apiVersion']=='v1'
                    key=ref['key']
                    if key in secret.get('stringData',{}): actual[entry['name']]=secret['stringData'][key]
                    else: actual[entry['name']]=base64.b64decode(secret['data'][key],validate=True).decode()
                else: raise ValueError('unexpected environment key')
            assert actual==service.get('environment',{})
            svc=objects[('Service',name)]; assert svc['apiVersion']=='v1' and namespace(svc)==namespace(dep)
            assert svc['spec']['selector'] and all(labels.get(k)==v for k,v in svc['spec']['selector'].items())
            assert svc['spec'].get('type','ClusterIP') in ('ClusterIP','NodePort','LoadBalancer')
            ports=svc['spec']['ports']
            named={p['name']:p['containerPort'] for p in container.get('ports',[]) if 'name' in p}
            assert all(type(p['port']) is int and type(p.get('targetPort',p['port'])) in (int,str) and p.get('protocol','TCP')=='TCP' for p in ports)
            if len(ports)>1: assert len({p['name'] for p in ports})==len(ports)
            target=lambda p: named[p['targetPort']] if isinstance(p.get('targetPort'),str) else p.get('targetPort',p['port'])
            assert sorted((p['port'],target(p)) for p in ports)==[(p,p) for p in sorted(service['expose'])]
            # Kubernetes has no depends_on: carry ordering through initContainer service waits.
            waits=pod.get('initContainers',[]); found=set()
            for wait in waits:
                # Offline executable-image contract: known BusyBox tags provide sh/nc/sleep.
                image=wait['image']; assert re.fullmatch(BUSYBOX,image) and (':' in image.split('@')[0].rsplit('/',1)[-1] or '@' in image)
                assert not any(wait.get(k) for k in ('args','env','envFrom','volumeMounts','restartPolicy','lifecycle'))
                command=wait['command']; assert len(command)==3 and command[0] in ('sh','/bin/sh') and command[1]=='-c'
                pairs=waited(command[2]); assert pairs
                for host,port in pairs:
                    assert host in service.get('depends_on',[]) and port in source[host]['expose']
                    found.add(host)
            assert found==set(service.get('depends_on',[]))
            if name=='proxy':
                volumes={v['name']:v for v in pod['volumes']}; mounts=container['volumeMounts']; mounted=False
                for mount in mounts:
                    if mount['mountPath']=='/etc/ingress' and mount.get('readOnly'):
                        secret=objects[('Secret',volumes[mount['name']]['secret']['secretName'])]; assert namespace(secret)==namespace(dep)
                        material=secret.get('stringData',{}).get('ingress.key')
                        if material is None: material=base64.b64decode(secret['data']['ingress.key'],validate=True).decode()
                        # The contract names the generated PEM file; tolerate only its final LF.
                        assert material.removesuffix('\n')==built['certs/ingress.key'].removesuffix('\n')
                        mounted=True
                assert mounted
        # Selectors must pick only their own service's pods; a shared label routes traffic to every pod.
        pods={name:objects[('Deployment',name)]['spec']['template']['metadata']['labels'] for name in source}
        for name in source:
            for kind,selector in (('Deployment',objects[('Deployment',name)]['spec']['selector']['matchLabels']),('Service',objects[('Service',name)]['spec']['selector'])):
                assert [other for other,labels in pods.items() if all(labels.get(k)==v for k,v in selector.items())]==[name]
        return True,'eight services, ports, credentials, dependency waits and ingress PEM preserved'
    except (OSError,ValueError,KeyError,TypeError,AssertionError,yaml.YAMLError):
        return False,'manifest migration contract incomplete or incorrect'

from pathlib import Path
import m2_tasks as mt

def baseline():
    task=mt.load_task(Path(__file__).resolve().parent)
    folder=task.dir/'workspace'
    built={p.relative_to(folder).as_posix():task.fill(p.read_text()) for p in folder.rglob('*') if p.is_file()}
    return task,built
