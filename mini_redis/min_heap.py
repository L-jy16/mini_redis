"""(expire_at, key) 최소 힙. 자체 해시맵으로 키의 위치를 추적한다."""
from .hash_map import HashMap


class MinHeap:
    """키당 한 항목만 유지하여 TTL 재설정/삭제 시 낡은 항목이 쌓이지 않는다."""

    def __init__(self):
        self._items = []
        self._positions = HashMap()  # key → 힙 배열 인덱스. 임의 키 삭제 시 전체 탐색을 피한다.

    def size(self):
        return len(self._items)

    # 최소값은 항상 0번 위치이므로 전체 탐색 없이 O(1)에 확인한다.
    def peek(self):
        return self._items[0] if self._items else None

    def _swap(self, a, b):
        self._items[a], self._items[b] = self._items[b], self._items[a]
        # 배열 위치를 바꾸면 위치 맵도 함께 갱신해야 다음 삭제/수정이 정확하다.
        self._positions.put(self._items[a][1], a)
        self._positions.put(self._items[b][1], b)

    def _heapify_up(self, index):
        while index > 0:
            parent = (index - 1) // 2  # 완전 이진 트리를 배열로 표현했을 때 부모 인덱스.
            if self._items[parent] <= self._items[index]:
                break
            self._swap(parent, index)
            index = parent
        return index

    def _heapify_down(self, index):
        while 2 * index + 1 < self.size():
            # 왼쪽 자식은 2*i+1, 오른쪽 자식은 2*i+2. 더 작은 쪽과 비교한다.
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
        # 우선순위가 작아졌거나 커졌을 수 있으므로 위·아래 방향을 모두 복구한다.
        index = self._heapify_up(index)
        self._heapify_down(index)

    def remove(self, key):
        """임의 키도 위치 맵을 이용해 평균 O(log n)에 실제 제거한다."""
        index = self._positions.remove(key)
        if index is None:
            return None
        removed = self._items[index]
        # 마지막 항목으로 삭제 위치를 채워 배열 중간을 당기는 O(n) 작업을 피한다.
        last = self._items.pop()
        if index < self.size():
            self._items[index] = last
            self._positions.put(last[1], index)
            index = self._heapify_up(index)
            self._heapify_down(index)
        return removed

    def pop(self):
        return None if not self._items else self.remove(self._items[0][1])
