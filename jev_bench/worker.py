"""One HTTP attempt per child process, bounded by the parent on every platform."""

import json
import sys
import urllib.error

from .config import loads
from .providers import request_classification


def main() -> int:
    try:
        request = loads(sys.stdin.buffer.read())
        result = request_classification(request["model"], request["dataset"],
                                        request["text"], request["timeout"])
        result["ok"] = True
    except (OSError, ValueError, TypeError, KeyError) as error:
        result = {"ok": False, "error_type": type(error).__name__,
                  "http_status": error.code if isinstance(error, urllib.error.HTTPError) else None}
        if isinstance(error, urllib.error.HTTPError):
            error.close()
    print(json.dumps(result, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
