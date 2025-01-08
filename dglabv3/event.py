import asyncio
from typing import Callable, Any, Dict, List
import functools
import logging


logger = logging.getLogger("dglabv3.event")


def event(name: str = None):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        event_name = name or func.__name__.removeprefix("on_")

        if not hasattr(func, "__self__"):

            def register_to_instance(instance):
                instance.register_event(event_name, wrapper)

            wrapper._register = register_to_instance

        return wrapper

    return decorator


class EventEmitter:
    def __init__(self):
        self._events: Dict[str, List[Callable]] = {}

    def register_event(self, event_name: str, callback: Callable) -> None:
        if event_name not in self._events:
            self._events[event_name] = []
        self._events[event_name].append(callback)
        logger.debug(f"已註冊事件 {event_name}")

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        logger.debug(f"觸發事件: {event_name}")
        if event_name in self._events:
            for callback in self._events[event_name]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(*args, **kwargs))
                    else:
                        callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"事件處理錯誤: {e}")
        else:
            logger.debug(f"沒有註冊的事件處理器: {event_name}")

    def event(self, name=None):
        def decorator(func):
            wrapped = event(name)(func)
            if hasattr(wrapped, "_register"):
                wrapped._register(self)
            return wrapped

        return decorator
