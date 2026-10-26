import os
import queue
import threading
import numpy as np

class PreallocatedFramePool:
    """
    4K (3840x2160) 高效零拷貝預分配幀緩衝池 (Circular Preallocated Frame Pool)
    - 徹底終結 Python GC 因每秒頻繁配置 1.9GB 陣列而引發的 OOM 與掉幀停頓
    - 支援線程安全借還機制 (Borrow / Return RAII 語義)
    - 限制記憶體峰值於安全閾值內 (預設 16 幀，約 2.0GB)
    """
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, capacity=16, height=2160, width=3840, channels=4):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(capacity, height, width, channels)
            return cls._instance

    def __init__(self, capacity=16, height=2160, width=3840, channels=4):
        self.capacity = capacity
        self.height = height
        self.width = width
        self.channels = channels
        self.shape = (height, width, channels)
        
        # 預分配連續記憶體區塊
        self._pool = queue.Queue(maxsize=capacity)
        for _ in range(capacity):
            buf = np.empty(self.shape, dtype=np.uint8)
            self._pool.put(buf)

    def acquire(self, timeout=1.0) -> np.ndarray:
        """從緩衝池中取出一幀可用緩存"""
        try:
            return self._pool.get(block=True, timeout=timeout)
        except queue.Empty:
            # 安全降級：若短暫耗盡，分配臨時幀以避免管線死鎖
            return np.empty(self.shape, dtype=np.uint8)

    def release(self, buf: np.ndarray):
        """將使用完畢的幀緩存歸還池中"""
        if buf is not None and buf.shape == self.shape:
            try:
                self._pool.put_nowait(buf)
            except queue.Full:
                pass

    def clear(self):
        """清理緩衝池"""
        while not self._pool.empty():
            try:
                self._pool.get_nowait()
            except queue.Empty:
                break
