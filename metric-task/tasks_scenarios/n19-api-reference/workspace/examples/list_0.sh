#!/bin/sh
curl --max-time 5 -H 'Authorization: Bearer {{secret:token_0}}' http://local.invalid/v1/orders
