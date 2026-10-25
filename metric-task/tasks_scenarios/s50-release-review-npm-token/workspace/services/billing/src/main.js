import http from "node:http";
http.createServer((req,res)=>{res.end("billing ready");}).listen(8082);
