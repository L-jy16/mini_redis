"""명령어 파싱과 Redis 스타일 출력. 저장소 로직과 터미널 입출력을 분리한다."""
import json
import shlex

from .store import MiniRedis

INTEGER_ERROR = "(error) ERR value is not an integer or out of range"


def parse_integer(token):
    """ASCII 부호/숫자만 허용하고 signed 64-bit 범위를 검사한다."""
    # 부호를 제외한 부분이 숫자인지 검사한다. 소수나 1_000 같은 표현은 거부한다.
    digits = token[1:] if token.startswith(("+", "-")) else token
    if not digits or any(char < "0" or char > "9" for char in digits):
        raise ValueError(INTEGER_ERROR)
    value = int(token)
    if value < -(2 ** 63) or value > 2 ** 63 - 1:
        raise ValueError(INTEGER_ERROR)
    return value


def quote(value):
    # 한글은 그대로 표시하고 값 안의 따옴표·줄바꿈은 이스케이프한다.
    return json.dumps(value, ensure_ascii=False)


class CommandProcessor:
    """execute는 문자열 응답을 반환하고 정상 종료 요청에만 None을 반환한다."""

    def __init__(self, store=None):
        self.store = MiniRedis() if store is None else store

    def execute(self, line):
        try:
            # SET name "Alice Kim"을 세 항목으로 분리한다. 따옴표 안 공백은 보존한다.
            args = shlex.split(line, comments=False)
        except ValueError:
            return "(error) ERR unbalanced quotes or invalid escape"
        if not args:
            return ""
        # 명령어만 대문자로 바꾸며 키와 값의 대소문자는 유지한다.
        command = args[0].upper()
        # expected는 명령어 이름까지 포함한 항목 수이다. SET key value는 3개이다.
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
            # SET key value: 저장 후 OK. TTL 초기화와 LRU 갱신은 저장소가 담당한다.
            if command == "SET":
                self.store.set(args[1], args[2])
                return "OK"
            # GET key: 존재하면 따옴표로 감싼 값, 없거나 만료되면 (nil).
            if command == "GET":
                value = self.store.get(args[1])
                return "(nil)" if value is None else quote(value)
            # DEL key: 삭제 성공은 1, 없는 키는 0.
            if command == "DEL":
                value = self.store.delete(args[1])
            # EXISTS key: 존재 여부만 확인하고 LRU 순서는 바꾸지 않는다.
            elif command == "EXISTS":
                value = self.store.exists(args[1])
            # DBSIZE: 만료된 키를 정리한 뒤 현재 키 개수를 반환한다.
            elif command == "DBSIZE":
                value = self.store.dbsize()
            # TTL key: 남은 초, 만료 시간 없음은 -1, 없는 키는 -2.
            elif command == "TTL":
                value = self.store.ttl(args[1])
            # EXPIRE key seconds: 정수 초를 받아 TTL을 설정하며 0 이하이면 즉시 삭제한다.
            elif command == "EXPIRE":
                value = self.store.expire(args[1], parse_integer(args[2]))
            # KEYS: 전체 키를 1부터 번호 매겨 출력한다. 패턴 검색은 지원하지 않는다.
            elif command == "KEYS":
                keys = self.store.keys()
                return "\n".join("{}. {}".format(i, quote(key))
                                 for i, key in enumerate(keys, 1)) or "(empty array)"
            # CONFIG SET maxmemory bytes: 0은 무제한, 양수는 UTF-8 바이트 제한이다.
            elif command == "CONFIG":
                if args[1].upper() != "SET" or args[2].lower() != "maxmemory":
                    return "(error) ERR unsupported CONFIG option"
                limit = parse_integer(args[3])
                if limit < 0:
                    return INTEGER_ERROR
                self.store.configure_maxmemory(limit)
                return "OK"
            # INFO memory: 현재 사용량, 설정한 제한, LRU 누적 제거 수를 출력한다.
            elif command == "INFO":
                if args[1].lower() != "memory":
                    return "(error) ERR unsupported INFO section"
                return self.store.memory_info()
            # 숫자를 반환하는 명령들의 공통 출력 형식이다.
            return "(integer) {}".format(value)
        except ValueError:
            return INTEGER_ERROR
        except MemoryError as error:
            return "(error) OOM {}".format(error)


def main():
    """EOF, Ctrl+C, exit, quit으로 안전하게 종료하는 대화형 REPL."""
    processor = CommandProcessor()
    # REPL: 입력(Read) → 실행(Evaluate) → 출력(Print)을 반복(Loop)한다.
    # python3 main.py와 테스트 실행 명령은 이 프롬프트가 아닌 일반 터미널에 입력한다.
    while True:
        try:
            line = input("mini-redis> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        result = processor.execute(line)
        # exit/quit은 None을 반환한다. 빈 입력의 빈 문자열과 구별한다.
        if result is None:
            break
        if result:
            print(result)
