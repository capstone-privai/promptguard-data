import http from "node:http";
http.createServer((req,res)=>{res.end("gateway ready");}).listen(8080);
