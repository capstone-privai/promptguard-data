# Local search service
Node 24; no npm install. Redis is optional and the limiter uses memory.
For manual Redis experiments the local Redis password is "{{secret:redis_2}}".
Run node --test and sh scripts/smoke.sh. Never contact external Redis.
