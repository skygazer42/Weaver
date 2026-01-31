"""
异步任务取消管理模块

提供优雅的任务取消机制，支持：
- 单任务取消
- 批量任务取消
- 取消状态检查
- 资源清理
- 检查点系统
- 清理回调
"""

import asyncio
import functools
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CancellationCheckpoint(Enum):
    """预定义的取消检查点"""

    BEFORE_LLM_CALL = "before_llm_call"
    AFTER_LLM_CALL = "after_llm_call"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    BEFORE_SEARCH = "before_search"
    AFTER_SEARCH = "after_search"
    BEFORE_CRAWL = "before_crawl"
    AFTER_CRAWL = "after_crawl"
    LOOP_ITERATION = "loop_iteration"
    NODE_ENTRY = "node_entry"
    NODE_EXIT = "node_exit"


@dataclass
class CancellationToken:
    """
    单个任务的取消令牌

    用于在长时间运行的任务中检查取消状态
    """

    task_id: str
    _cancelled: bool = field(default=False, repr=False)
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    created_at: datetime = field(default_factory=datetime.now)
    cancelled_at: Optional[datetime] = field(default=None)
    status: TaskStatus = field(default=TaskStatus.PENDING)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 清理回调
    _cleanup_callbacks: List[Callable[[], Awaitable[None]]] = field(
        default_factory=list, repr=False
    )
    # 检查点记录
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    # 当前检查点
    current_checkpoint: str = field(default="")

    @property
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._cancelled

    def cancel(self, reason: str = "User requested cancellation"):
        """
        触发取消

        Args:
            reason: 取消原因
        """
        if not self._cancelled:
            self._cancelled = True
            self.cancelled_at = datetime.now()
            self.status = TaskStatus.CANCELLED
            self.metadata["cancel_reason"] = reason
            self._event.set()
            logger.info(f"Task {self.task_id} cancelled: {reason}")

    def check(self, checkpoint: Union[str, CancellationCheckpoint] = ""):
        """
        检查取消状态，如果已取消则抛出 CancelledError

        在长时间操作的关键点调用此方法

        Args:
            checkpoint: 可选的检查点标识
        """
        checkpoint_name = (
            checkpoint.value if isinstance(checkpoint, CancellationCheckpoint) else checkpoint
        )

        if checkpoint_name:
            self.current_checkpoint = checkpoint_name
            self.checkpoints.append(
                {
                    "checkpoint": checkpoint_name,
                    "timestamp": datetime.now().isoformat(),
                }
            )

        if self._cancelled:
            raise asyncio.CancelledError(
                f"Task {self.task_id} was cancelled at checkpoint '{checkpoint_name}': {self.metadata.get('cancel_reason', 'Unknown')}"
            )

    def register_cleanup(self, callback: Callable[[], Awaitable[None]]):
        """
        注册清理回调

        当任务被取消时，这些回调会被调用来清理资源

        Args:
            callback: 异步清理函数
        """
        self._cleanup_callbacks.append(callback)

    async def run_cleanup(self):
        """运行所有清理回调"""
        for callback in reversed(self._cleanup_callbacks):
            try:
                await callback()
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")
        self._cleanup_callbacks.clear()

    def mark_running(self):
        """标记任务开始运行"""
        self.status = TaskStatus.RUNNING

    def mark_paused(self):
        """标记任务暂停"""
        self.status = TaskStatus.PAUSED

    def mark_completed(self):
        """标记任务完成"""
        if not self._cancelled:
            self.status = TaskStatus.COMPLETED

    def mark_failed(self, error: str):
        """标记任务失败"""
        if not self._cancelled:
            self.status = TaskStatus.FAILED
            self.metadata["error"] = error

    async def wait_for_cancel(self, timeout: Optional[float] = None) -> bool:
        """
        等待取消信号

        Args:
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            是否收到取消信号
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "is_cancelled": self._cancelled,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "current_checkpoint": self.current_checkpoint,
            "checkpoint_count": len(self.checkpoints),
            "metadata": self.metadata,
        }


class CancellationManager:
    """
    全局取消管理器

    管理所有任务的取消令牌，提供统一的取消接口
    """

    def __init__(self):
        self._tokens: Dict[str, CancellationToken] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        # 全局取消回调
        self._global_cancel_callbacks: List[Callable[[str, str], Awaitable[None]]] = []

    def register_global_cancel_callback(self, callback: Callable[[str, str], Awaitable[None]]):
        """
        注册全局取消回调

        当任何任务被取消时调用

        Args:
            callback: 回调函数，接收 (task_id, reason) 参数
        """
        self._global_cancel_callbacks.append(callback)

    async def create_token(
        self, task_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> CancellationToken:
        """
        创建新的取消令牌

        Args:
            task_id: 任务 ID
            metadata: 任务元数据

        Returns:
            取消令牌
        """
        async with self._lock:
            # 如果存在同 ID 的旧令牌，先取消它
            if task_id in self._tokens:
                old_token = self._tokens[task_id]
                if not old_token.is_cancelled:
                    old_token.cancel("Replaced by new task")
                    await old_token.run_cleanup()
                logger.debug(f"Replaced existing token for task {task_id}")

            token = CancellationToken(task_id=task_id, metadata=metadata or {})
            self._tokens[task_id] = token
            logger.debug(f"Created cancellation token for task {task_id}")
            return token

    def create_token_sync(
        self, task_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> CancellationToken:
        """
        同步创建取消令牌（用于非异步上下文）

        Args:
            task_id: 任务 ID
            metadata: 任务元数据

        Returns:
            取消令牌
        """
        # 如果存在同 ID 的旧令牌，先取消它
        if task_id in self._tokens:
            old_token = self._tokens[task_id]
            if not old_token.is_cancelled:
                old_token.cancel("Replaced by new task")
            logger.debug(f"Replaced existing token for task {task_id}")

        token = CancellationToken(task_id=task_id, metadata=metadata or {})
        self._tokens[task_id] = token
        logger.debug(f"Created cancellation token for task {task_id}")
        return token

    async def cancel(self, task_id: str, reason: str = "User requested") -> bool:
        """
        取消指定任务

        Args:
            task_id: 任务 ID
            reason: 取消原因

        Returns:
            是否成功取消（任务存在则返回 True）
        """
        async with self._lock:
            if task_id in self._tokens:
                token = self._tokens[task_id]
                token.cancel(reason)
                await token.run_cleanup()

                # 调用全局回调
                for callback in self._global_cancel_callbacks:
                    try:
                        await callback(task_id, reason)
                    except Exception as e:
                        logger.warning(f"Global cancel callback failed: {e}")

                return True
            logger.warning(f"Task {task_id} not found for cancellation")
            return False

    def cancel_sync(self, task_id: str, reason: str = "User requested") -> bool:
        """
        同步取消任务

        Args:
            task_id: 任务 ID
            reason: 取消原因

        Returns:
            是否成功取消
        """
        if task_id in self._tokens:
            self._tokens[task_id].cancel(reason)
            return True
        return False

    async def cancel_all(self, reason: str = "Batch cancellation"):
        """
        取消所有任务

        Args:
            reason: 取消原因
        """
        async with self._lock:
            count = 0
            for token in self._tokens.values():
                if not token.is_cancelled:
                    token.cancel(reason)
                    await token.run_cleanup()
                    count += 1
            logger.info(f"Cancelled {count} tasks")

    def get_token(self, task_id: str) -> Optional[CancellationToken]:
        """
        获取指定任务的令牌

        Args:
            task_id: 任务 ID

        Returns:
            取消令牌或 None
        """
        return self._tokens.get(task_id)

    def is_cancelled(self, task_id: str) -> bool:
        """
        检查任务是否已取消

        Args:
            task_id: 任务 ID

        Returns:
            是否已取消
        """
        token = self._tokens.get(task_id)
        return token.is_cancelled if token else False

    async def cleanup(self, max_age_seconds: int = 3600):
        """
        清理过期令牌

        Args:
            max_age_seconds: 最大保留时间（秒）
        """
        async with self._lock:
            now = datetime.now()
            expired = []

            for task_id, token in self._tokens.items():
                age = (now - token.created_at).total_seconds()
                if age > max_age_seconds:
                    expired.append(task_id)

            for task_id in expired:
                del self._tokens[task_id]

            if expired:
                logger.info(f"Cleaned up {len(expired)} expired cancellation tokens")

    async def start_cleanup_task(self, interval_seconds: int = 600):
        """
        启动后台清理任务

        Args:
            interval_seconds: 清理间隔（秒）
        """

        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                await self.cleanup()

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(f"Started cleanup task with interval {interval_seconds}s")

    async def stop_cleanup_task(self):
        """停止后台清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped cleanup task")

    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有活跃任务信息

        Returns:
            任务 ID -> 任务信息 的映射
        """
        return {
            task_id: token.to_dict()
            for task_id, token in self._tokens.items()
            if token.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED)
        }

    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息

        Returns:
            统计数据
        """
        stats = {status.value: 0 for status in TaskStatus}
        for token in self._tokens.values():
            stats[token.status.value] += 1
        stats["total"] = len(self._tokens)
        return stats


# 全局实例
cancellation_manager = CancellationManager()


def check_cancellation(task_id: str, checkpoint: Union[str, CancellationCheckpoint] = ""):
    """
    便捷函数：检查任务是否已取消

    如果已取消则抛出 asyncio.CancelledError

    Args:
        task_id: 任务 ID
        checkpoint: 可选的检查点标识
    """
    token = cancellation_manager.get_token(task_id)
    if token:
        token.check(checkpoint)


def check_state_cancellation(
    state: Dict[str, Any], checkpoint: Union[str, CancellationCheckpoint] = ""
):
    """
    便捷函数：从 state 中检查取消状态

    Args:
        state: Agent state 字典
        checkpoint: 可选的检查点标识
    """
    # 检查 state 中的取消标志
    if state.get("is_cancelled"):
        raise asyncio.CancelledError("Task was cancelled (state flag)")

    # 检查取消令牌
    token_id = state.get("cancel_token_id")
    if token_id:
        check_cancellation(token_id, checkpoint)


def cancellable(func: Callable) -> Callable:
    """
    装饰器：使异步函数可取消

    被装饰的函数需要第一个参数包含 task_id 或 cancel_token_id

    使用示例:
        @cancellable
        async def long_running_task(state):
            # state 需要包含 cancel_token_id
            ...
    """

    async def wrapper(*args, **kwargs):
        # 尝试从参数中获取 task_id
        task_id = None

        # 检查 kwargs
        task_id = kwargs.get("task_id") or kwargs.get("cancel_token_id")

        # 检查第一个参数（通常是 state）
        if not task_id and args:
            first_arg = args[0]
            if isinstance(first_arg, dict):
                task_id = first_arg.get("cancel_token_id") or first_arg.get("task_id")

        # 执行前检查
        if task_id:
            check_cancellation(task_id)

        try:
            result = await func(*args, **kwargs)

            # 执行后检查
            if task_id:
                check_cancellation(task_id)

            return result

        except asyncio.CancelledError:
            logger.info(f"Function {func.__name__} cancelled")
            raise

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


class CancellableContext:
    """
    上下文管理器：提供可取消的执行上下文

    使用示例:
        async with CancellableContext(task_id) as ctx:
            ctx.check()  # 检查取消
            await some_operation()
            ctx.check()  # 再次检查
    """

    def __init__(self, task_id: str, auto_cleanup: bool = True):
        self.task_id = task_id
        self.auto_cleanup = auto_cleanup
        self.token: Optional[CancellationToken] = None

    async def __aenter__(self) -> "CancellableContext":
        self.token = await cancellation_manager.create_token(self.task_id)
        self.token.mark_running()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            if exc_type is asyncio.CancelledError:
                pass  # 已经是取消状态
            elif exc_type:
                self.token.mark_failed(str(exc_val))
            else:
                self.token.mark_completed()

        return False  # 不抑制异常

    def check(self):
        """检查取消状态"""
        if self.token:
            self.token.check()

    @property
    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self.token.is_cancelled if self.token else False
