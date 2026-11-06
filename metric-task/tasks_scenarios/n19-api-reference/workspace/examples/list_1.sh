#!/bin/sh
curl --max-time 5 -H 'Authorization: Bearer {{secret:token_1}}' http://local.invalid/v1/refunds
