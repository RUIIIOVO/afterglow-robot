from __future__ import annotations

import logging

"""日志初始化工具。"""


def setup_logging(verbose: bool = False) -> None:
    """按运行模式初始化统一日志格式。"""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
