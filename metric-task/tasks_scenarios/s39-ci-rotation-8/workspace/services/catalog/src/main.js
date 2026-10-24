import http from "node:http";
http.createServer((req,res)=>{res.end("catalog ready");}).listen(8081);
