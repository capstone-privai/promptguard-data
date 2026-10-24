import http from "node:http";
http.createServer((req,res)=>{res.end("indexer ready");}).listen(8084);
