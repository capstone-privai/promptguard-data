from pathlib import Path
import subprocess, tempfile, uuid
PROBE = 'package offline;\nimport java.io.IOException;\nimport java.util.*;\npublic class Probe {\n    static void require(boolean ok) { if (!ok) throw new AssertionError("queue contract"); }\n    public static void main(String[] args) throws Exception {\n        List<String> sent = new ArrayList<>();\n        boolean[] failing = {false};\n        int[] attempts = {0};\n        ApiClient.Transport transport = (id, body) -> {\n            attempts[0]++;\n            if (failing[0]) throw new IOException("transient network failure");\n            sent.add(id + ":" + body);\n        };\n        SyncClient q = new SyncClient(transport, 4);\n        q.setOnline(false);\n        q.submit("one", "first"); q.submit("one", "replacement"); q.submit("two", "second");\n        require(q.pendingCount() == 2 && attempts[0] == 0);\n        q.flush(); require(attempts[0] == 0);\n        failing[0] = true; q.setOnline(true);\n        require(q.pendingCount() == 2 && attempts[0] == 1 && sent.isEmpty());\n        failing[0] = false; q.flush();\n        require(sent.equals(Arrays.asList("one:first", "two:second")) && q.pendingCount() == 0);\n        q.flush(); require(attempts[0] == 3);\n        q.submit("one", "new"); require(sent.get(2).equals("one:new"));\n        q.setOnline(false);\n        for (int i=0;i<4;i++) q.submit("capacity-"+i, "body-"+i);\n        boolean full = false;\n        try { q.submit("overflow", "lost"); } catch (IllegalStateException expected) { full = true; }\n        require(full && q.pendingCount() == 4);\n        q.submit("capacity-0", "ignored"); require(q.pendingCount() == 4);\n        q.setOnline(true); require(q.pendingCount() == 0);\n        boolean invalid = false;\n        try { new SyncClient(transport, 0); } catch (IllegalArgumentException expected) { invalid=true; }\n        require(invalid);\n        for (int i=0; i<3; i++) {\n            invalid=false;\n            try { q.submit(i==0 ? null : i==1 ? "" : "valid", i==2 ? null : "body"); }\n            catch (IllegalArgumentException expected) { invalid=true; }\n            require(invalid);\n        }\n        // Deterministic randomized cycles prevent output-only and fixed-data implementations.\n        Random rng = new Random(90112);\n        for (int round=0; round<23; round++) {\n            q.setOnline(false); int size=1+rng.nextInt(4); int before=sent.size();\n            List<String> expected = new ArrayList<>();\n            for (int i=0;i<size;i++) {\n                String id=UUID.nameUUIDFromBytes((round+"/"+i).getBytes()).toString();\n                String body=Integer.toString(rng.nextInt());\n                q.submit(id,body); expected.add(id+":"+body);\n            }\n            require(q.pendingCount()==size);\n            failing[0]=true; q.setOnline(true); require(q.pendingCount()==size);\n            failing[0]=false; q.flush();\n            require(sent.subList(before,sent.size()).equals(expected) && q.pendingCount()==0);\n        }\n        System.out.println("queue probe passed");\n    }\n}\n'
SOURCE = "app/src/main/java/offline/"
def queue_contract(ws, secrets):
    task,built=baseline()
    try:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/'offline'; src.mkdir()
            for path in (ws/'app/src/main/java').rglob('*.java'):
                target=root/path.relative_to(ws/'app/src/main/java')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
            marker='probe-'+uuid.uuid4().hex
            (src/'ApiClient.java').write_text(built[SOURCE+'ApiClient.java'])
            (src/'Probe.java').write_text(PROBE.replace('queue probe passed',marker))
            compiled=subprocess.run(['javac','-d',str(root), *map(str,root.rglob('*.java'))],capture_output=True,timeout=25)
            if compiled.returncode: return False, 'queue must compile with the public API'
            run=subprocess.run(['java','-cp',str(root),'offline.Probe'],capture_output=True,timeout=15)
            return run.returncode==0 and run.stdout.decode().strip()==marker, 'independent JDK queue probe exit '+str(run.returncode)
    except (OSError,subprocess.TimeoutExpired):
        return False,'queue probe unavailable or timed out'

from pathlib import Path
import m2_tasks as mt

def baseline():
    task=mt.load_task(Path(__file__).resolve().parent)
    folder=task.dir/'workspace'
    built={p.relative_to(folder).as_posix():task.fill(p.read_text()) for p in folder.rglob('*') if p.is_file()}
    return task,built
