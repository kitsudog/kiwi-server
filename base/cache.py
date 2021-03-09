import requests

from base.style import now

__pool = {

}


def cache_http_get(url: str, expire=24 * 3600 * 1000) -> bytes:
    """
    支持cache的get操作
    """
    key = f"cache_http_get#{url}"
    if key not in __pool:
        rsp = requests.get(url)
        if rsp.status_code == 200:
            content = rsp.content
            __pool[key] = {
                "content": content,
                "expire": now() + expire
            }
    return __pool[key]["content"]
