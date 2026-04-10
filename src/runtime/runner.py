from __future__ import annotations

import json
import traceback
from typing import Callable

from src.runtime.errors import AfterglowError


def run_cli(handler: Callable[[], int]) -> int:
    try:
        return handler()
    except AfterglowError as error:
        print(f"[错误] {error.user_message}")
        if error.context:
            print(json.dumps({"code": error.code, "context": error.context}, ensure_ascii=False))
        return 1
    except Exception as error:  # noqa: BLE001
        print("[错误] 未预期异常，请查看调试上下文。")
        print(json.dumps({"error": str(error), "traceback": traceback.format_exc()}, ensure_ascii=False))
        return 1

