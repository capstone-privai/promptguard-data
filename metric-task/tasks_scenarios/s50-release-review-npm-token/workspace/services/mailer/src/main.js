import http from "node:http";
http.createServer((req,res)=>{res.end("mailer ready");}).listen(8083);
