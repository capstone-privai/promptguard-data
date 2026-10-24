import http from "node:http";
http.createServer((req,res)=>{res.end("worker ready");}).listen(8087);
