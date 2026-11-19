"""GoodThings Studio 商品短视频业务层。"""

__all__ = ["GoodThingsService"]


def __getattr__(name: str):
    if name == "GoodThingsService":
        from goodthings.service import GoodThingsService

        return GoodThingsService
    raise AttributeError(name)
