import api.index as root
from api.index import handler as RootHandler

if (root_app := getattr(root, "app", None)) is not None:
    app = root_app


class handler(RootHandler):
    pass
