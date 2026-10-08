"""문자열 저장소, UTF-8 메모리 집계, LRU 제거 및 힙 기반 TTL."""
import time

from .hash_map import HashMap
from .linked_list import DoublyLinkedList
from .min_heap import MinHeap


class Entry:
    """데이터와 LRU 노드 참조를 함께 저장해 검색 후 이동을 O(1)에 한다."""

    def __init__(self, value, node):
        self.value = value
        self.node = node
        self.expire_at = None


class MiniRedis:
    """단일 스레드 메모리 저장소. 테스트에서는 clock을 주입할 수 있다."""

    def __init__(self, clock=None):
        self._clock = time.monotonic if clock is None else clock
        self._data = HashMap()
        self._lru = DoublyLinkedList()
        self._expiry = MinHeap()
        self.used_memory = 0
        self.maxmemory = 0
        self.evicted_keys = 0

    @staticmethod
    def _bytes(key, value):
        return len(key.encode("utf-8")) + len(value.encode("utf-8"))

    def _delete(self, key):
        entry = self._data.remove(key)
        if entry is None:
            return False
        self.used_memory -= self._bytes(key, entry.value)
        self._lru.remove_node(entry.node)
        self._expiry.remove(key)
        return True

    def purge_expired(self):
        """각 명령 전에 힙의 루트부터 만료된 키만 제거한다."""
        now = self._clock()
        while self._expiry.peek() is not None and self._expiry.peek()[0] <= now:
            self._delete(self._expiry.peek()[1])

    def _evict(self):
        while self.maxmemory > 0 and self.used_memory > self.maxmemory:
            self._delete(self._lru.tail.data)
            self.evicted_keys += 1

    def set(self, key, value):
        self.purge_expired()
        size = self._bytes(key, value)
        # 실패한 SET이 기존 값/TTL/LRU 또는 다른 키를 파괴하지 않도록 선검사.
        if self.maxmemory > 0 and size > self.maxmemory:
            raise MemoryError("command not allowed when used_memory > 'maxmemory'")
        entry = self._data.get(key)
        if entry is None:
            entry = Entry(value, self._lru.insert_front(key))
            self._data.put(key, entry)
        else:
            self.used_memory -= self._bytes(key, entry.value)
            entry.value = value
            entry.expire_at = None
            self._expiry.remove(key)
            self._lru.move_to_front(entry.node)
        self.used_memory += size
        self._evict()

    def get(self, key):
        self.purge_expired()
        entry = self._data.get(key)
        if entry is None:
            return None
        self._lru.move_to_front(entry.node)
        return entry.value

    def delete(self, key):
        self.purge_expired()
        return int(self._delete(key))

    def exists(self, key):
        self.purge_expired()
        return int(self._data.contains(key))

    def dbsize(self):
        self.purge_expired()
        return self._data.size()

    def keys(self):
        self.purge_expired()
        return self._data.keys()

    def configure_maxmemory(self, limit):
        if not isinstance(limit, int) or limit < 0:
            raise ValueError("maxmemory must be a non-negative integer")
        self.purge_expired()
        self.maxmemory = limit
        self._evict()

    def memory_info(self):
        self.purge_expired()
        return ("used_memory:{}\nmaxmemory:{}\nevicted_keys:{}".format(
            self.used_memory, self.maxmemory, self.evicted_keys))

    def expire(self, key, seconds):
        self.purge_expired()
        entry = self._data.get(key)
        if entry is None:
            return 0
        if seconds <= 0:
            self._delete(key)
        else:
            entry.expire_at = self._clock() + seconds
            self._expiry.push((entry.expire_at, key))
        return 1

    def ttl(self, key):
        self.purge_expired()
        entry = self._data.get(key)
        if entry is None:
            return -2
        if entry.expire_at is None:
            return -1
        remaining = entry.expire_at - self._clock()
        if remaining <= 0:
            self._delete(key)
            return -2
        return int(remaining)
