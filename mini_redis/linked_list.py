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

    def _attach_front(self, node):
        node.owner = self
        node.prev = None
        node.next = self.head
        if self.head is None:
            self.tail = node
        else:
            self.head.prev = node
        self.head = node
        self.size += 1
        return node

    def insert_front(self, data):
        return self._attach_front(Node(data))

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
        if node.prev is None:
            self.head = node.next
        else:
            node.prev.next = node.next
        if node.next is None:
            self.tail = node.prev
        else:
            node.next.prev = node.prev
        node.prev = node.next = node.owner = None
        self.size -= 1
        return node.data

    def remove_front(self):
        return None if self.head is None else self.remove_node(self.head)

    def remove_back(self):
        return None if self.tail is None else self.remove_node(self.tail)

    def move_to_front(self, node):
        if node.owner is not self:
            raise ValueError("node does not belong to this list")
        if node is not self.head:
            self.remove_node(node)
            self._attach_front(node)

    def __iter__(self):
        node = self.head
        while node is not None:
            yield node.data
            node = node.next
