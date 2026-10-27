"""Deliver background Python work to Qt without accessing widgets from workers."""

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Slot, Qt


class JobPool(QObject):
    """Own a small executor and deliver all completion callbacks on the GUI thread."""

    finished = Signal(int, object, object)

    def __init__(self, parent=None):
        """Create two workers for inference/file work and bounded preview preparation."""
        super().__init__(parent)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="idframe")
        self._callbacks = {}
        self._next_id = 0
        self.finished.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    @property
    def busy(self):
        """Include completed futures whose GUI result has not yet been consumed."""
        return bool(self._callbacks)

    def submit(self, work, callback):
        """Run a callable and deliver its result or exception to one GUI callback."""
        self._next_id += 1
        token = self._next_id
        self._callbacks[token] = callback
        future = self.executor.submit(work)

        def completed(result):
            """Emit data only; widget updates belong to the queued receiver."""
            try:
                value, error = result.result(), None
            except Exception as problem:
                value, error = None, problem
            self.finished.emit(token, value, error)

        future.add_done_callback(completed)
        return token

    @Slot(int, object, object)
    def _deliver(self, token, value, error):
        """Remove the tracked task before consuming its completion on the GUI thread."""
        callback = self._callbacks.pop(token, None)
        if callback is not None:
            callback(value, error)

    def shutdown(self):
        """Release idle worker resources after every queued GUI callback is consumed."""
        if self.busy:
            raise RuntimeError("Background work is still active")
        self.executor.shutdown(wait=False, cancel_futures=True)
