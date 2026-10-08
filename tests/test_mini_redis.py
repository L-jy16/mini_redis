"""외부 패키지 및 실제 대기 없이 필수 요구사항과 구조 불변식을 검증한다."""
import ast
from pathlib import Path
import random
import subprocess
import sys
import unittest

from mini_redis.cli import CommandProcessor, INTEGER_ERROR
from mini_redis.hash_map import HashMap
from mini_redis.linked_list import DoublyLinkedList
from mini_redis.min_heap import MinHeap
from mini_redis.store import MiniRedis


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class StructureTests(unittest.TestCase):
    def test_list_endpoints_and_moves(self):
        linked = DoublyLinkedList()
        self.assertIsNone(linked.remove_front())
        self.assertIsNone(linked.remove_back())
        a = linked.insert_front("a")
        b = linked.insert_back("b")
        c = linked.insert_back("c")
        linked.move_to_front(b)
        linked.move_to_front(b)
        self.assertEqual(list(linked), ["b", "a", "c"])
        self.assertIs(linked.head.next.prev, b)
        self.assertEqual(linked.remove_node(a), "a")
        self.assertEqual(linked.remove_back(), "c")
        self.assertEqual(linked.remove_front(), "b")
        self.assertEqual(linked.size, 0)
        self.assertIsNone(linked.head)
        self.assertIsNone(linked.tail)
        with self.assertRaises(ValueError):
            linked.remove_node(c)

    def test_hash_collisions_resize_and_none(self):
        class CollisionMap(HashMap):
            @staticmethod
            def _hash(key):
                return 0
        table = CollisionMap(4)
        for i in range(3):
            table.put(str(i), i)
        self.assertEqual(table.capacity, 4)
        table.put("3", 3)
        self.assertEqual(table.capacity, 8)
        for i in range(4, 100):
            table.put(str(i), i)
        for i in range(100):
            self.assertEqual(table.get(str(i)), i)
        table.put("0", None)
        self.assertTrue(table.contains("0"))
        self.assertEqual(table.size(), 100)
        for i in range(1, 100, 2):
            self.assertEqual(table.remove(str(i)), i)
        self.assertEqual(table.size(), 50)
        self.assertEqual(sorted(table.keys()), sorted(str(i) for i in range(0, 100, 2)))
        self.assertIsNone(table.remove("absent"))

    def test_heap_order_update_remove(self):
        heap = MinHeap()
        self.assertIsNone(heap.pop())
        self.assertIsNone(heap.peek())
        for item in [(10, "a"), (5, "b"), (5, "c"), (20, "d")]:
            heap.push(item)
        heap.push((1, "d"))
        self.assertEqual(heap.peek(), (1, "d"))
        heap.push((30, "d"))
        self.assertEqual(heap.size(), 4)
        self.assertEqual(heap.remove("c"), (5, "c"))
        self.assertIsNone(heap.remove("missing"))
        self.assertEqual([heap.pop(), heap.pop(), heap.pop()], [(5, "b"), (10, "a"), (30, "d")])
        self.assertEqual(heap._positions.size(), 0)

    def test_heap_randomized_against_sorted_array(self):
        rng = random.Random(41)
        heap = MinHeap()
        reference = []
        for _ in range(1500):
            key = str(rng.randrange(100))
            if rng.randrange(3):
                item = (rng.randrange(200), key)
                reference = [old for old in reference if old[1] != key]
                reference.append(item)
                heap.push(item)
            else:
                reference = [old for old in reference if old[1] != key]
                heap.remove(key)
            self.assertEqual(heap.size(), len(reference))
            self.assertEqual(heap.peek(), min(reference) if reference else None)
            for i, item in enumerate(heap._items):
                self.assertEqual(heap._positions.get(item[1]), i)
                if i:
                    self.assertLessEqual(heap._items[(i - 1) // 2], item)
        self.assertEqual([heap.pop() for _ in range(heap.size())], sorted(reference))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.db = MiniRedis(self.clock)

    def test_utf8_and_overwrite_accounting(self):
        self.db.set("이름", "홍길동")
        self.assertEqual(self.db.used_memory, 15)
        self.db.set("이름", "A")
        self.assertEqual(self.db.used_memory, 7)
        self.assertEqual(self.db.delete("이름"), 1)
        self.assertEqual(self.db.used_memory, 0)
        self.assertEqual(self.db.delete("이름"), 0)

    def test_pdf_example(self):
        self.db.configure_maxmemory(30)
        for key, value in [("user:1", "Alice"), ("user:2", "Bob"), ("user:3", "Charlie")]:
            self.db.set(key, value)
        self.assertIsNone(self.db.get("user:1"))
        self.assertEqual(self.db.memory_info(), "used_memory:22\nmaxmemory:30\nevicted_keys:1")

    def test_successful_get_and_set_touch_lru(self):
        self.db.configure_maxmemory(4)
        self.db.set("a", "1")
        self.db.set("b", "2")
        self.db.get("a")
        self.db.set("c", "3")
        self.assertFalse(self.db.exists("b"))
        self.db.set("a", "4")
        self.db.set("d", "5")
        self.assertFalse(self.db.exists("c"))
        self.assertEqual(self.db.evicted_keys, 2)

    def test_other_commands_do_not_touch_lru(self):
        self.db.configure_maxmemory(4)
        self.db.set("a", "1")
        self.db.set("b", "2")
        self.db.exists("a")
        self.db.expire("a", 10)
        self.db.ttl("a")
        self.db.keys()
        self.db.dbsize()
        self.db.memory_info()
        self.db.get("absent")
        self.db.set("c", "3")
        self.assertFalse(self.db.exists("a"))
        self.assertEqual(self.db._expiry.size(), 0)

    def test_oom_is_atomic_and_preserves_ttl(self):
        self.db.configure_maxmemory(4)
        self.db.set("a", "1")
        self.db.set("b", "2")
        self.db.expire("a", 10)
        for key in ("a", "new"):
            with self.assertRaises(MemoryError):
                self.db.set(key, "12345")
        self.assertEqual(self.db.ttl("a"), 10)
        self.assertEqual(list(self.db._lru), ["b", "a"])
        self.assertEqual(self.db.used_memory, 4)
        self.assertEqual(self.db.evicted_keys, 0)
        self.assertEqual(self.db.get("a"), "1")

    def test_limit_reduction_and_unlimited(self):
        for key in ("a", "b", "c"):
            self.db.set(key, "1")
        self.db.configure_maxmemory(2)
        self.assertEqual(self.db.keys(), ["c"])
        self.assertEqual(self.db.evicted_keys, 2)
        self.db.configure_maxmemory(0)
        self.db.set("large", "x" * 100)
        self.assertEqual(self.db.dbsize(), 2)

    def test_ttl_status_boundary_and_reset(self):
        self.assertEqual(self.db.ttl("a"), -2)
        self.assertEqual(self.db.expire("a", 10), 0)
        self.db.set("a", "1")
        self.assertEqual(self.db.ttl("a"), -1)
        self.assertEqual(self.db.expire("a", 3), 1)
        self.clock.now += 0.1
        self.assertEqual(self.db.ttl("a"), 2)
        self.clock.now = 103
        self.assertIsNone(self.db.get("a"))
        self.assertEqual(self.db.ttl("a"), -2)
        self.assertEqual(self.db._lru.size, 0)
        self.assertEqual(self.db._expiry.size(), 0)
        self.assertEqual(self.db.used_memory, 0)
        self.assertEqual(self.db.evicted_keys, 0)

    def test_expire_update_overwrite_and_recreate(self):
        self.db.set("a", "old")
        self.db.expire("a", 1)
        self.db.expire("a", 10)
        self.assertEqual(self.db._expiry.size(), 1)
        self.clock.now += 2
        self.assertEqual(self.db.get("a"), "old")
        self.db.set("a", "new")
        self.assertEqual(self.db._expiry.size(), 0)
        self.assertEqual(self.db.ttl("a"), -1)
        self.db.expire("a", 1)
        self.db.delete("a")
        self.db.set("a", "reborn")
        self.clock.now += 20
        self.assertEqual(self.db.get("a"), "reborn")

    def test_immediate_expire(self):
        for seconds in (0, -10):
            self.db.set("a", "1")
            self.assertEqual(self.db.expire("a", seconds), 1)
            self.assertEqual(self.db.ttl("a"), -2)
            self.assertEqual(self.db.used_memory, 0)

    def test_aggregate_commands_purge_and_no_false_eviction(self):
        for operation in (self.db.keys, self.db.dbsize, self.db.memory_info):
            self.db.set("a", "1")
            self.db.expire("a", 1)
            self.clock.now += 1
            operation()
            self.assertEqual(self.db._data.size(), 0)
        self.db.configure_maxmemory(2)
        self.db.set("a", "1")
        self.db.expire("a", 1)
        self.clock.now += 1
        self.db.set("b", "2")
        self.assertEqual(self.db.evicted_keys, 0)

    def test_mixed_operations_preserve_all_structures(self):
        rng = random.Random(5)
        for _ in range(1000):
            key = str(rng.randrange(30))
            action = rng.randrange(6)
            if action == 0:
                self.db.set(key, "한글" * rng.randrange(3))
            elif action == 1:
                self.db.delete(key)
            elif action == 2:
                self.db.expire(key, rng.randrange(-1, 8))
            elif action == 3:
                self.clock.now += 1
                self.db.purge_expired()
            elif action == 4:
                self.db.get(key)
            else:
                self.db.configure_maxmemory(rng.randrange(20, 80))
            keys = self.db.keys()
            self.assertEqual(sorted(keys), sorted(self.db._lru))
            self.assertEqual(self.db._lru.size, len(keys))
            total = 0
            expiring = 0
            for stored in keys:
                entry = self.db._data.get(stored)
                total += len(stored.encode()) + len(entry.value.encode())
                expiring += int(entry.expire_at is not None)
            self.assertEqual(self.db.used_memory, total)
            self.assertEqual(self.db._expiry.size(), expiring)
            if self.db.maxmemory:
                self.assertLessEqual(total, self.db.maxmemory)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.cli = CommandProcessor(MiniRedis(FakeClock()))

    def test_strings_quotes_and_commands(self):
        for command, expected in [
            ('set name "Alice Kim"', 'OK'), ('GET name', '"Alice Kim"'),
            ('SET "" ""', 'OK'), ('GET ""', '""'), ('DBSIZE', '(integer) 2'),
            ('EXISTS name', '(integer) 1'), ('DEL name', '(integer) 1'),
            ('GET name', '(nil)'), ('DEL name', '(integer) 0'),
            ('EXPIRE missing 3', '(integer) 0'), ('TTL missing', '(integer) -2'),
            ('DEL ""', '(integer) 1'), ('KEYS', '(empty array)'), ('', ''),
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.cli.execute(command), expected)
        self.assertIsNone(self.cli.execute('quit'))
        self.assertIsNone(self.cli.execute('EXIT'))

    def test_errors_and_recovery(self):
        self.assertEqual(self.cli.execute('HELLO'), "(error) ERR unknown command 'HELLO'")
        self.assertEqual(self.cli.execute('GET'), "(error) ERR wrong number of arguments for 'GET' command")
        for command in ('SET a', 'KEYS *', 'DBSIZE a', 'quit a', 'CONFIG SET maxmemory', 'INFO'):
            self.assertIn('wrong number of arguments', self.cli.execute(command))
        for token in ('abc', '1.2', '1_000', '１２', '9223372036854775808', '9' * 5000):
            self.assertEqual(self.cli.execute('CONFIG SET maxmemory ' + token), INTEGER_ERROR)
            self.assertEqual(self.cli.execute('EXPIRE a ' + token), INTEGER_ERROR)
        self.assertEqual(self.cli.execute('CONFIG SET maxmemory -1'), INTEGER_ERROR)
        self.assertIn('(error)', self.cli.execute('SET a "broken'))
        self.assertIn('(error)', self.cli.execute('CONFIG GET maxmemory 3'))
        self.assertIn('(error)', self.cli.execute('INFO other'))
        self.assertEqual(self.cli.execute('CONFIG SET maxmemory 1'), 'OK')
        self.assertEqual(self.cli.execute('SET a b'), "(error) OOM command not allowed when used_memory > 'maxmemory'")
        self.assertEqual(self.cli.execute('CONFIG SET maxmemory 0'), 'OK')
        self.assertEqual(self.cli.execute('SET a b'), 'OK')
        self.assertEqual(self.cli.execute('KEYS'), '1. "a"')

    def test_real_cli_process_and_eof(self):
        root = Path(__file__).resolve().parents[1]
        for entrypoint in ([sys.executable, 'main.py'], [sys.executable, '-m', 'mini_redis']):
            result = subprocess.run(entrypoint, input='SET a "hello world"\nGET a\nquit\n',
                                    text=True, capture_output=True, cwd=str(root), timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('mini-redis> OK', result.stdout)
            self.assertIn('mini-redis> "hello world"', result.stdout)
        result = subprocess.run([sys.executable, 'main.py'], input='', text=True,
                                capture_output=True, cwd=str(root), timeout=5)
        self.assertEqual(result.returncode, 0)

    def test_no_forbidden_collections_and_python38_syntax(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / 'mini_redis').glob('*.py'):
            tree = ast.parse(path.read_text(), feature_version=(3, 8))
            for node in ast.walk(tree):
                self.assertNotIsInstance(node, (ast.Dict, ast.DictComp, ast.Set, ast.SetComp))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ('dict', 'set', 'hash'))
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split('.')[0], ('collections', 'heapq'))
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], ('collections', 'heapq'))


if __name__ == '__main__':
    unittest.main()
