import http from "node:http";
http.createServer((req,res)=>{res.end("exporter ready");}).listen(8085);
