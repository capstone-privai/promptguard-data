import os

import redis

# The API reads product pages from the cache database in CACHE_URL.
cache = redis.Redis.from_url(os.environ["CACHE_URL"])


def get_product(product_id: str):
    return cache.get(f"product:{product_id}")
