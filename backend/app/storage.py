from __future__ import annotations

import threading

from app.schemas import TaskState


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskState] = {}

    def save_task(self, task: TaskState) -> None:
        with self._lock:
            self._tasks[task.id] = task.model_copy(deep=True)

    def get_task(self, task_id: str) -> TaskState | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.model_copy(deep=True) if task else None
