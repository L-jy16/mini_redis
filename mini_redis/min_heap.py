"""(expire_at, key) 최소 힙. 자체 해시맵으로 키의 위치를 추적한다."""
from .hash_map import HashMap


class MinHeap:
    """키당 한 항목만 유지하여 TTL 재설정/삭제 시 낡은 항목이 쌓이지 않는다."""

    def __init__(self):
        self._items = []
        self._positions = HashMap()

    def size(self):
        return len(self._items)

    def peek(self):
        return self._items[0] if self._items else None

    def _swap(self, a, b):
        self._items[a], self._items[b] = self._items[b], self._items[a]
        self._positions.put(self._items[a][1], a)
        self._positions.put(self._items[b][1], b)

    def _heapify_up(self, index):
        while index > 0:
            parent = (index - 1) // 2
            if self._items[parent] <= self._items[index]:
                break
            self._swap(parent, index)
            index = parent
        return index

    def _heapify_down(self, index):
        while 2 * index + 1 < self.size():
            child = 2 * index + 1
            if child + 1 < self.size() and self._items[child + 1] < self._items[child]:
                child += 1
            if self._items[index] <= self._items[child]:
                break
            self._swap(index, child)
            index = child

    def push(self, item):
        """새 키를 삽입하거나 기존 키의 만료 시각을 O(log n)에 갱신한다."""
        index = self._positions.get(item[1])
        if index is None:
            index = self.size()
            self._items.append(item)
            self._positions.put(item[1], index)
        else:
            self._items[index] = item
        index = self._heapify_up(index)
        self._heapify_down(index)

    def remove(self, key):
        """임의 키도 위치 맵을 이용해 평균 O(log n)에 실제 제거한다."""
        index = self._positions.remove(key)
        if index is None:
            return None
        removed = self._items[index]
        last = self._items.pop()
        if index < self.size():
            self._items[index] = last
            self._positions.put(last[1], index)
            index = self._heapify_up(index)
            self._heapify_down(index)
        return removed

    def pop(self):
        return None if not self._items else self.remove(self._items[0][1])
