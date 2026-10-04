from typing import Optional

__all__ = ["DGLabError", "NotSupportedError", "AppResponseError"]


class DGLabError(Exception):
    """dglabv3 錯誤基底類別"""


class NotSupportedError(DGLabError):
    """目前的協議或設備不支援此操作"""


class AppResponseError(DGLabError):
    """AppError (僅 V4)"""

    def __init__(self, code: str, method: Optional[str] = None) -> None:
        self.code = code
        self.method = method
        super().__init__(f"{method}: {code}" if method else code)
