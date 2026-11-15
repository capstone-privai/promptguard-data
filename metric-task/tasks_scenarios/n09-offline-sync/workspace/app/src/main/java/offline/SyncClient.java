package offline;
import java.io.IOException;

/** API contract is documented in README.md. The old adapter has no offline queue. */
public class SyncClient {
    private final ApiClient.Transport transport;
    public SyncClient(ApiClient.Transport transport, int capacity) { this.transport = transport; }
    public void setOnline(boolean value) throws IOException { }
    public void submit(String id, String body) throws IOException { transport.post(id, body); }
    public void flush() throws IOException { }
    public int pendingCount() { return 0; }
}
