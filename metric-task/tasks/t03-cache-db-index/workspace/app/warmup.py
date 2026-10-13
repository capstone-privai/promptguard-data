import os
from urllib.parse import urlsplit

import redis

# The nightly warmup job fills the product cache. Product pages always live in database 0,
# shared with the storefront renderer; the session store uses its own database.
PRODUCT_CACHE_DB = 0


def connect():
    url = urlsplit(os.environ["CACHE_URL"])
    return redis.Redis(host=url.hostname, port=url.port, password=url.password, db=PRODUCT_CACHE_DB)


def warm(products):
    client = connect()
    for product in products:
        client.set(f"product:{product['id']}", product["html"], ex=int(os.environ.get("CACHE_TTL_SECONDS", "300")))
