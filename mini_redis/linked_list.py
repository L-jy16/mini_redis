"""LRU와 해시 충돌 체인에서 공유하는 O(1) 이중 연결 리스트."""


class Node:
    """연결 정보와 데이터를 보관한다. owner로 잘못된 삭제를 방지한다."""

    def __init__(self, data):
        self.data = data
        self.prev = None
        self.next = None
        self.owner = None


class DoublyLinkedList:
    """head가 앞, tail이 뒤인 리스트. 노드를 알면 삭제/이동은 O(1)."""

    def __init__(self):
        self.head = None
        self.tail = None
        self.size = 0

    # 새 노드 생성과 기존 노드 이동에서 공유한다. 앞쪽 연결만 바꾸므로 O(1)이다.
    def _attach_front(self, node):
        node.owner = self
        node.prev = None
        node.next = self.head
        # 빈 리스트에서는 삽입한 노드가 head와 tail을 모두 맡는다.
        if self.head is None:
            self.tail = node
        else:
            self.head.prev = node
        self.head = node
        self.size += 1
        return node

    def insert_front(self, data):
        return self._attach_front(Node(data))

    # tail을 직접 참조하므로 마지막 노드를 찾는 순회 없이 O(1)에 삽입한다.
    def insert_back(self, data):
        node = Node(data)
        node.owner = self
        node.prev = self.tail
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self.size += 1
        return node

    def remove_node(self, node):
        """노드를 분리하고 데이터를 반환한다. 다른 리스트의 노드는 거부한다."""
        if node.owner is not self:
            raise ValueError("node does not belong to this list")
        # 앞·뒤 이웃을 서로 연결한다. 양 끝 노드라면 head 또는 tail도 수정한다.
        if node.prev is None:
            self.head = node.next
        else:
            node.prev.next = node.next
        if node.next is None:
            self.tail = node.prev
        else:
            node.next.prev = node.prev
        # 분리된 노드의 연결을 끊어 중복 삭제와 다른 리스트의 잘못된 사용을 방지한다.
        node.prev = node.next = node.owner = None
        self.size -= 1
        return node.data

    def remove_front(self):
        return None if self.head is None else self.remove_node(self.head)

    def remove_back(self):
        return None if self.tail is None else self.remove_node(self.tail)

    # 노드를 새로 만들지 않고 분리 후 앞에 재연결한다. 두 작업 모두 O(1)이다.
    def move_to_front(self, node):
        if node.owner is not self:
            raise ValueError("node does not belong to this list")
        if node is not self.head:
            self.remove_node(node)
            self._attach_front(node)

    def __iter__(self):
        node = self.head
        while node is not None:
            # yield는 데이터를 하나씩 전달해 for문에서 리스트를 순회할 수 있게 한다.
            yield node.data
            node = node.next
