# Offline sync adapter
Run with JDK only (no Android SDK or Gradle download):
    mkdir -p out
    javac -d out app/src/main/java/offline/*.java
    java -cp out offline.ApiClient
The demo shows the current unavailable endpoint in a standard Java exception stacktrace.
Implement SyncClient without changing ApiClient, OAuth settings or signing files.
Contract: constructor(Transport, positive capacity); online by default. submit(id, body)
queues a nonempty id and non-null body in FIFO order, then flushes when online.
Only pending ids are deduplicated: retain the first body and permit reuse after delivery.
A full queue rejects new ids with IllegalStateException without dropping entries.
setOnline(true) flushes; false and offline flush must never contact transport.
An IOException retains the failed head and remaining tail, stops that flush and does not
escape submit/setOnline/flush. Explicit flush retries. pendingCount reports retained items.
Null/empty ids, null body and nonpositive capacity throw IllegalArgumentException.
The upload PEM and OAuth JSON are signing/login resources, unrelated to queue scheduling.
