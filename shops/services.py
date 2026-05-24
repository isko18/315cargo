from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Shop


def build_shop_open_url(shop, user):
    if shop.client_code_strategy != Shop.ClientCodeStrategy.QUERY_PARAM:
        return shop.url
    query_param_name = shop.query_param_name or "client_code"
    parts = urlsplit(shop.url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[query_param_name] = user.client_code
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
