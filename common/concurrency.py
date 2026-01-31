"""
批量并发控制模块

提供 API 调用的并发限制、速率控制和批量处理功能。
"""

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ConcurrencyController:
    """
    批量并发控制器

    功能:
    - 信号量限制并发数
    - API 调用速率限制
    - 批量任务处理

    使用示例:
        controller = ConcurrencyController(max_concurrency=5)
        results = await controller.gather_with_limit([task1, task2, ...])
    """

    def __init__(
        self,
        max_concurrency: int = 5,
        rate_limit: float = 0.0,  # 秒，0 表示无限制
    ):
        self.max_concurrency = max_concurrency
        self.rate_limit = rate_limit
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._last_call_time: float = 0
        self._rate_lock = asyncio.Lock()

        logger.info(f"ConcurrencyController initialized: max_concurrency={max_concurrency}, rate_limit={rate_limit}s")

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """延迟初始化信号量（确保在事件循环中创建）"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
        return self._semaphore

    async def _apply_rate_limit(self):
        """应用速率限制"""
        if self.rate_limit <= 0:
            return

        async with self._rate_lock:
            now = time.time()
            elapsed = now - self._last_call_time
            wait_time = self.rate_limit - elapsed

            if wait_time > 0:
                logger.debug(f"Rate limit: waiting {wait_time:.3f}s")
                await asyncio.sleep(wait_time)

            self._last_call_time = time.time()

    async def run_with_limit(self, coro: Awaitable[T]) -> T:
        """
        单个任务带并发限制执行

        Args:
            coro: 要执行的协程

        Returns:
            协程执行结果
        """
        async with self.semaphore:
            await self._apply_rate_limit()
            return await coro

    async def gather_with_limit(
        self,
        tasks: List[Awaitable[T]],
        return_exceptions: bool = True
    ) -> List[T]:
        """
        批量任务带并发限制执行

        Args:
            tasks: 协程列表
            return_exceptions: 是否将异常作为结果返回

        Returns:
            结果列表（与输入顺序对应）
        """
        async def limited_task(task: Awaitable[T]) -> T:
            async with self.semaphore:
                await self._apply_rate_limit()
                return await task

        logger.info(f"Executing {len(tasks)} tasks with concurrency limit {self.max_concurrency}")

        results = await asyncio.gather(
            *[limited_task(t) for t in tasks],
            return_exceptions=return_exceptions
        )

        # 统计成功/失败
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Completed: {success_count}/{len(tasks)} successful")

        return results

    async def batch_process(
        self,
        items: List[Any],
        processor: Callable[[Any], Awaitable[T]],
        batch_size: Optional[int] = None,
        on_batch_complete: Optional[Callable[[int, int], None]] = None
    ) -> List[T]:
        """
        分批处理列表项

        Args:
            items: 要处理的项目列表
            processor: 处理单个项目的异步函数
            batch_size: 每批大小，默认等于 max_concurrency
            on_batch_complete: 批次完成回调 (completed_count, total_count)

        Returns:
            处理结果列表
        """
        batch_size = batch_size or self.max_concurrency
        results: List[T] = []
        total = len(items)

        logger.info(f"Batch processing {total} items, batch_size={batch_size}")

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            batch_num = i // batch_size + 1

            logger.debug(f"Processing batch {batch_num}, items {i+1}-{min(i+batch_size, total)}")

            batch_tasks = [processor(item) for item in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            results.extend(batch_results)

            if on_batch_complete:
                on_batch_complete(len(results), total)

        return results

    async def map_with_limit(
        self,
        func: Callable[[Any], Awaitable[T]],
        items: List[Any]
    ) -> List[T]:
        """
        并发 map 操作

        类似 asyncio.gather，但带并发限制

        Args:
            func: 异步映射函数
            items: 输入项列表

        Returns:
            映射结果列表
        """
        tasks = [self.run_with_limit(func(item)) for item in items]
        return await asyncio.gather(*tasks, return_exceptions=True)


class RateLimiter:
    """
    简单的速率限制器

    使用令牌桶算法控制 API 调用频率
    """

    def __init__(
        self,
        calls_per_second: float = 1.0,
        burst: int = 1
    ):
        self.calls_per_second = calls_per_second
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """获取一个令牌（如果没有可用令牌则等待）"""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now

            # 补充令牌
            self.tokens = min(self.burst, self.tokens + elapsed * self.calls_per_second)

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.calls_per_second
                logger.debug(f"RateLimiter: waiting {wait_time:.3f}s for token")
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


def with_concurrency_limit(controller: ConcurrencyController):
    """
    装饰器：为异步函数添加并发限制

    使用示例:
        @with_concurrency_limit(controller)
        async def fetch_data(url):
            ...
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await controller.run_with_limit(func(*args, **kwargs))
        return wrapper
    return decorator


# 默认全局实例（延迟初始化，在实际使用时根据配置创建）
_default_controller: Optional[ConcurrencyController] = None


def get_concurrency_controller() -> ConcurrencyController:
    """获取默认并发控制器"""
    global _default_controller
    if _default_controller is None:
        from .config import settings
        _default_controller = ConcurrencyController(
            max_concurrency=getattr(settings, 'max_concurrency', 5),
            rate_limit=getattr(settings, 'api_rate_limit', 0.5)
        )
    return _default_controller


def reset_concurrency_controller():
    """重置默认控制器（用于测试或配置更新）"""
    global _default_controller
    _default_controller = None
