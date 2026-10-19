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
        # monotonic은 시스템 날짜 변경으로 역행하지 않는 경과 시간용 시계이다.
        self._clock = time.monotonic if clock is None else clock
        # 데이터 조회용 해시맵, 최근 사용 순서용 리스트, 만료 순서용 힙을 함께 관리한다.
        self._data = HashMap()
        self._lru = DoublyLinkedList()
        self._expiry = MinHeap()
        self.used_memory = 0
        self.maxmemory = 0  # 0이면 메모리 사용량에 제한을 두지 않는다.
        self.evicted_keys = 0

    @staticmethod
    def _bytes(key, value):
        # 문자 수가 아닌 UTF-8 바이트 수를 합산한다. 노드·버킷 오버헤드는 제외한다.
        return len(key.encode("utf-8")) + len(value.encode("utf-8"))

    def _delete(self, key):
        # DEL, TTL 만료, LRU 제거가 공유하는 삭제 경로: 세 자료구조를 함께 정리한다.
        entry = self._data.remove(key)
        if entry is None:
            return False
        self.used_memory -= self._bytes(key, entry.value)
        self._lru.remove_node(entry.node)
        self._expiry.remove(key)
        return True

    def purge_expired(self):
        """각 명령 전에 힙의 루트부터 만료된 키만 제거한다."""
        # 명령 처리 시 정리하며 유휴 중에는 실행하지 않는다. 힙 루트가 가장 빠른 만료이다.
        now = self._clock()
        while self._expiry.peek() is not None and self._expiry.peek()[0] <= now:
            self._delete(self._expiry.peek()[1])

    def _evict(self):
        while self.maxmemory > 0 and self.used_memory > self.maxmemory:
            # tail은 가장 오래 사용하지 않은 키이다. 제한 이하가 될 때까지 반복 제거한다.
            self._delete(self._lru.tail.data)
            self.evicted_keys += 1  # 직접 DEL과 TTL 만료는 이 카운터에 포함하지 않는다.

    def set(self, key, value):
        self.purge_expired()
        size = self._bytes(key, value)
        # 실패한 SET이 기존 값/TTL/LRU 또는 다른 키를 파괴하지 않도록 선검사.
        if self.maxmemory > 0 and size > self.maxmemory:
            raise MemoryError("command not allowed when used_memory > 'maxmemory'")
        entry = self._data.get(key)
        if entry is None:
            # 새 키를 가장 최근 위치에 넣고 Entry에 해당 노드 참조를 보관한다.
            entry = Entry(value, self._lru.insert_front(key))
            self._data.put(key, entry)
        else:
            self.used_memory -= self._bytes(key, entry.value)
            entry.value = value
            # 기존 키 SET은 이전 만료 예약을 취소한다.
            entry.expire_at = None
            self._expiry.remove(key)
            self._lru.move_to_front(entry.node)
        self.used_memory += size
        self._evict()

    # GET: 만료 정리 → 평균 O(1) 해시 조회 → 성공한 경우만 O(1) LRU 이동.
    def get(self, key):
        self.purge_expired()
        entry = self._data.get(key)
        if entry is None:
            return None
        self._lru.move_to_front(entry.node)
        return entry.value

    # DEL: 내부 삭제 결과 True/False를 CLI에서 사용할 정수 1/0으로 변환한다.
    def delete(self, key):
        self.purge_expired()
        return int(self._delete(key))

    # EXISTS: 값을 읽거나 최근 사용 순서를 갱신하지 않고 존재 여부만 확인한다.
    def exists(self, key):
        self.purge_expired()
        return int(self._data.contains(key))

    # DBSIZE: 만료 데이터가 개수에 포함되지 않도록 먼저 정리한다.
    def dbsize(self):
        self.purge_expired()
        return self._data.size()

    # KEYS: 살아 있는 모든 키를 반환한다. 정렬 순서는 보장하지 않는다.
    def keys(self):
        self.purge_expired()
        return self._data.keys()

    def configure_maxmemory(self, limit):
        if not isinstance(limit, int) or limit < 0:
            raise ValueError("maxmemory must be a non-negative integer")
        self.purge_expired()
        # 제한을 낮췄다면 다음 SET을 기다리지 않고 여기서 바로 LRU 제거를 수행한다.
        self.maxmemory = limit
        self._evict()

    # INFO memory: 만료 삭제에 따른 사용량 감소까지 반영한 통계를 반환한다.
    def memory_info(self):
        self.purge_expired()
        return ("used_memory:{}\nmaxmemory:{}\nevicted_keys:{}".format(
            self.used_memory, self.maxmemory, self.evicted_keys))

    def expire(self, key, seconds):
        self.purge_expired()
        entry = self._data.get(key)
        if entry is None:
            return 0
        # EXPIRE: 0초와 음수는 즉시 삭제, 양수는 절대 만료 시각으로 변환한다.
        if seconds <= 0:
            self._delete(key)
        else:
            entry.expire_at = self._clock() + seconds
            # 같은 키가 이미 힙에 있으면 만료 시각을 교체하므로 예약이 중복되지 않는다.
            self._expiry.push((entry.expire_at, key))
        return 1

    def ttl(self, key):
        self.purge_expired()
        entry = self._data.get(key)
        if entry is None:
            return -2
        # TTL의 특수값: 없는 키는 위에서 -2, 만료 예약이 없는 키는 -1을 반환한다.
        if entry.expire_at is None:
            return -1
        remaining = entry.expire_at - self._clock()
        if remaining <= 0:
            self._delete(key)
            return -2
        # 양수의 소수 부분을 버린다. 남은 시간이 1초 미만이면 0이다.
        return int(remaining)
