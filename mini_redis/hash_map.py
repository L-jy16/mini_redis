"""내장 hash/dict 없이 UTF-8 해시와 연결 리스트 체이닝을 구현한다."""
from .linked_list import DoublyLinkedList


class HashMap:
    """문자열 키용 해시맵. 부하율이 0.75를 넘으면 버킷 수를 두 배로 늘린다."""

    def __init__(self, capacity=8):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._buckets = [None] * capacity
        self._size = 0

    @property
    def capacity(self):
        return len(self._buckets)

    @staticmethod
    def _hash(key):
        # 바이트마다 곱셈과 XOR로 섞고 64비트로 제한하는 FNV-1a 방식.
        result = 14695981039346656037
        for byte in key.encode("utf-8"):
            result = ((result ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
        return result

    def _find(self, key):
        bucket = self._buckets[self._hash(key) % self.capacity]
        node = None if bucket is None else bucket.head
        while node is not None:
            if node.data[0] == key:
                return node
            node = node.next
        return None

    def put(self, key, value):
        node = self._find(key)
        if node is not None:
            node.data = (key, value)
            return
        index = self._hash(key) % self.capacity
        if self._buckets[index] is None:
            self._buckets[index] = DoublyLinkedList()
        self._buckets[index].insert_back((key, value))
        self._size += 1
        if self._size * 4 > self.capacity * 3:
            old = self._buckets
            self._buckets = [None] * (self.capacity * 2)
            self._size = 0
            for bucket in old:
                if bucket is not None:
                    for key, value in bucket:
                        self.put(key, value)

    def get(self, key, default=None):
        node = self._find(key)
        return default if node is None else node.data[1]

    def remove(self, key):
        node = self._find(key)
        if node is None:
            return None
        value = node.data[1]
        node.owner.remove_node(node)
        self._size -= 1
        return value

    def contains(self, key):
        return self._find(key) is not None

    def keys(self):
        """내부 테이블을 노출하지 않고 키 목록을 반환한다."""
        result = []
        for bucket in self._buckets:
            if bucket is not None:
                for key, _ in bucket:
                    result.append(key)
        return result

    def size(self):
        return self._size
