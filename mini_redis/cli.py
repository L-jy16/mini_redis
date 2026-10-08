"""명령어 파싱과 Redis 스타일 출력. 저장소 로직과 터미널 입출력을 분리한다."""
import json
import shlex

from .store import MiniRedis

INTEGER_ERROR = "(error) ERR value is not an integer or out of range"


def parse_integer(token):
    """ASCII 부호/숫자만 허용하고 signed 64-bit 범위를 검사한다."""
    digits = token[1:] if token.startswith(("+", "-")) else token
    if not digits or any(char < "0" or char > "9" for char in digits):
        raise ValueError(INTEGER_ERROR)
    value = int(token)
    if value < -(2 ** 63) or value > 2 ** 63 - 1:
        raise ValueError(INTEGER_ERROR)
    return value


def quote(value):
    return json.dumps(value, ensure_ascii=False)


class CommandProcessor:
    """execute는 문자열 응답을 반환하고 정상 종료 요청에만 None을 반환한다."""

    def __init__(self, store=None):
        self.store = MiniRedis() if store is None else store

    def execute(self, line):
        try:
            args = shlex.split(line, comments=False)
        except ValueError:
            return "(error) ERR unbalanced quotes or invalid escape"
        if not args:
            return ""
        command = args[0].upper()
        if command in ("EXIT", "QUIT"):
            expected = 1
        elif command in ("SET", "EXPIRE"):
            expected = 3
        elif command in ("GET", "DEL", "EXISTS", "TTL", "INFO"):
            expected = 2
        elif command in ("DBSIZE", "KEYS"):
            expected = 1
        elif command == "CONFIG":
            expected = 4
        else:
            return "(error) ERR unknown command '{}'".format(args[0])
        if len(args) != expected:
            return "(error) ERR wrong number of arguments for '{}' command".format(command)
        if command in ("EXIT", "QUIT"):
            return None
        try:
            if command == "SET":
                self.store.set(args[1], args[2])
                return "OK"
            if command == "GET":
                value = self.store.get(args[1])
                return "(nil)" if value is None else quote(value)
            if command == "DEL":
                value = self.store.delete(args[1])
            elif command == "EXISTS":
                value = self.store.exists(args[1])
            elif command == "DBSIZE":
                value = self.store.dbsize()
            elif command == "TTL":
                value = self.store.ttl(args[1])
            elif command == "EXPIRE":
                value = self.store.expire(args[1], parse_integer(args[2]))
            elif command == "KEYS":
                keys = self.store.keys()
                return "\n".join("{}. {}".format(i, quote(key))
                                 for i, key in enumerate(keys, 1)) or "(empty array)"
            elif command == "CONFIG":
                if args[1].upper() != "SET" or args[2].lower() != "maxmemory":
                    return "(error) ERR unsupported CONFIG option"
                limit = parse_integer(args[3])
                if limit < 0:
                    return INTEGER_ERROR
                self.store.configure_maxmemory(limit)
                return "OK"
            elif command == "INFO":
                if args[1].lower() != "memory":
                    return "(error) ERR unsupported INFO section"
                return self.store.memory_info()
            return "(integer) {}".format(value)
        except ValueError:
            return INTEGER_ERROR
        except MemoryError as error:
            return "(error) OOM {}".format(error)


def main():
    """EOF, Ctrl+C, exit, quit으로 안전하게 종료하는 대화형 REPL."""
    processor = CommandProcessor()
    while True:
        try:
            line = input("mini-redis> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        result = processor.execute(line)
        if result is None:
            break
        if result:
            print(result)
