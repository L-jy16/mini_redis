"""내장 hash/dict 없이 UTF-8 해시와 연결 리스트 체이닝을 구현한다."""
from .linked_list import DoublyLinkedList, Node


class HashMap:
    """문자열 키용 해시맵. 부하율이 0.75를 넘으면 버킷 수를 두 배로 늘린다."""

    NODE_POOL_LIMIT = 64  # 해시맵마다 보관할 빈 체인 노드 수의 상한.

    def __init__(self, capacity=8):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._buckets = [None] * capacity
        self._size = 0
        # 고정 길이 배열을 스택처럼 사용한다. 키/값을 저장하는 해시맵 대체 용도가 아니다.
        self._node_pool = [None] * self.NODE_POOL_LIMIT
        self._pool_size = 0

    def _acquire_node(self, data):
        """풀의 노드를 O(1)에 꺼내고, 풀이 비었을 때만 새 Node를 생성한다."""
        if self._pool_size == 0:
            return Node(data)
        self._pool_size -= 1
        node = self._node_pool[self._pool_size]
        self._node_pool[self._pool_size] = None
        node.data = data
        return node

    def _release_node(self, node):
        """분리된 노드의 데이터 참조를 지우고 최대 64개까지만 보관한다."""
        # remove_node가 prev/next/owner를 해제한 후 호출한다.
        # 이전 키/값을 잡고 있지 않도록 상한 초과 시에도 data를 지운다.
        node.data = None
        if self._pool_size < self.NODE_POOL_LIMIT:
            self._node_pool[self._pool_size] = node
            self._pool_size += 1
        # 풀이 가득 차면 저장하지 않는다. 외부 참조가 없으면 Python이 회수한다.

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
        # 해시를 버킷 수로 나눈 나머지가 배열 인덱스이다. 충돌하면 체인을 순회한다.
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
            # 기존 키는 값만 교체하며 저장된 키 개수는 증가시키지 않는다.
            node.data = (key, value)
            return
        index = self._hash(key) % self.capacity
        if self._buckets[index] is None:
            self._buckets[index] = DoublyLinkedList()
        # 동일한 인덱스의 키들을 연결 리스트에 보관하는 체이닝 충돌 해결 방식이다.
        node = self._acquire_node((key, value))
        self._buckets[index].insert_back_node(node)
        self._size += 1
        # size / capacity > 0.75를 정수 곱셈으로 검사한다.
        if self._size * 4 > self.capacity * 3:
            old = self._buckets
            self._buckets = [None] * (self.capacity * 2)
            self._size = 0
            # 버킷 수가 바뀌면 나머지도 달라지므로 모든 키를 새 위치에 재삽입한다.
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
        self._release_node(node)
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
