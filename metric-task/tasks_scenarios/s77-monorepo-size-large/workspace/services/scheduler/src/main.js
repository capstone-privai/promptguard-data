import http from "node:http";
http.createServer((req,res)=>{res.end("scheduler ready");}).listen(8086);
