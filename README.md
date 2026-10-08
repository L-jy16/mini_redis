# Mini Redis

Python으로 해시맵, 이중 연결 리스트, 최소 힙을 직접 구현한 CLI 기반 문자열 저장소입니다.
`5-1.pdf`의 필수 요구사항을 대상으로 구현했으며 보너스 과제는 포함하지 않습니다.

## 실행

Python 3.8 이상이 필요합니다. 외부 패키지 설치는 필요하지 않습니다.
프로젝트 폴더에서 실행하세요.

```bash
python3 main.py
# 또는
python3 -m mini_redis
```

`mini-redis>` 프롬프트에 명령어를 입력합니다. `exit`, `quit`, EOF(Ctrl+D), Ctrl+C로 종료합니다.
데이터는 메모리에만 존재하며 프로그램을 종료하면 사라집니다.

```text
mini-redis> CONFIG SET maxmemory 30
OK
mini-redis> SET user:1 "Alice"
OK
mini-redis> SET user:2 "Bob"
OK
mini-redis> SET user:3 "Charlie"
OK
mini-redis> GET user:1
(nil)
mini-redis> INFO memory
used_memory:22
maxmemory:30
evicted_keys:1
mini-redis> EXPIRE user:2 3
(integer) 1
mini-redis> TTL user:2
(integer) 2
```

TTL 출력은 입력 사이에 흐른 시간에 따라 달라집니다. 3초가 지난 뒤 `GET user:2`는 `(nil)`,
`TTL user:2`는 `(integer) -2`를 반환합니다.

## 지원 명령어

명령어와 CONFIG/INFO 옵션은 대소문자를 구분하지 않습니다. 키와 값은 구분합니다.
공백 없는 문자열, 큰따옴표 및 작은따옴표로 감싼 문자열, 빈 문자열을 지원합니다.
따옴표와 역슬래시 처리는 Python `shlex`의 POSIX 규칙을 따릅니다.

| 명령어 | 동작 및 출력 |
| --- | --- |
| `SET key value` | 저장/덮어쓰기, TTL 초기화, LRU 갱신. `OK` |
| `GET key` | 값의 따옴표 문자열 또는 `(nil)`. 성공한 조회만 LRU 갱신 |
| `DEL key` | 데이터·LRU·TTL 항목 삭제. `(integer) 1` 또는 `0` |
| `EXISTS key` | 존재 여부. `(integer) 1` 또는 `0` |
| `DBSIZE` | 만료되지 않은 키 수. `(integer) N` |
| `KEYS` | 번호가 붙은 전체 키 목록 또는 `(empty array)`. 패턴 인자 없음 |
| `CONFIG SET maxmemory bytes` | UTF-8 바이트 기준 제한 설정. 0은 무제한. `OK` |
| `INFO memory` | `used_memory`, `maxmemory`, `evicted_keys` 출력 |
| `EXPIRE key seconds` | TTL 설정. 성공 시 `1`, 없는 키 `0`. 0 이하이면 즉시 삭제 |
| `TTL key` | 남은 초를 내림한 정수. 없는 키 `-2`, TTL 없는 키 `-1` |

숫자 결과는 모두 `(integer) N` 형식입니다. 정수는 ASCII 숫자와 선택적 부호를 허용하며
signed 64-bit 범위를 검사합니다. `maxmemory`는 음수를 허용하지 않습니다.

```text
GET
(error) ERR wrong number of arguments for 'GET' command
HELLO
(error) ERR unknown command 'HELLO'
CONFIG SET maxmemory abc
(error) ERR value is not an integer or out of range
```

## 파일 구조

```text
main.py                     실행 진입점
mini_redis/
  __init__.py               MiniRedis 공개 API
  __main__.py               python3 -m mini_redis 진입점
  linked_list.py            노드 및 이중 연결 리스트
  hash_map.py               UTF-8 해시와 체이닝 해시맵
  min_heap.py               키 위치 추적이 가능한 최소 힙
  store.py                  문자열 저장소, LRU, TTL, 메모리 집계
  cli.py                    파싱, 명령어 분기, 응답 형식, REPL
tests/
  test_mini_redis.py         자료구조·명령어·통합 테스트
```

## 자료구조와 동작 원리

### 해시맵

UTF-8 바이트를 순회하며 XOR와 곱셈으로 64비트 해시를 계산합니다(FNV-1a 방식 직접 구현).
`해시 % 버킷 수`로 위치를 정하고, 충돌한 항목은 직접 구현한 이중 연결 리스트에 연결합니다.
Python의 `hash()`를 사용하지 않습니다. 로드 팩터가 0.75를 **초과**하면 버킷을 두 배로 늘리고
모든 항목의 위치를 다시 계산합니다. 기존 키의 값 교체는 키 수를 늘리지 않습니다.

`put/get/remove/contains`는 평균 O(1), 충돌이 집중되면 O(n)입니다.
리사이즈는 O(n)이며 삽입의 평균 상환 비용에 포함됩니다. 문자열 해시 계산은 키 바이트 길이에 비례합니다.

### 이중 연결 리스트와 LRU

노드는 `prev`, `next`, `data`를 가지며 `owner`로 소속을 검증합니다.
`insert_front/insert_back/remove_front/remove_back/remove_node/move_to_front`를 모두 구현했습니다.
각 연산은 리스트를 순회하지 않고 포인터만 변경하므로 O(1)입니다.

LRU 리스트의 앞은 가장 최근, 뒤는 가장 오래 사용한 키입니다. 해시맵의 엔트리에 LRU 노드 참조를
저장하므로, `SET` 또는 성공한 `GET`에서 해당 노드를 찾기 위해 리스트를 순회하지 않습니다.
`EXISTS`, `TTL`, `EXPIRE`, `KEYS`, `DBSIZE`, `INFO`는 접근 순서를 바꾸지 않습니다.

### 메모리 제한

```text
used_memory = 모든 키에 대한 (len(key.encode('utf-8')) + len(value.encode('utf-8')))의 합
```

자료구조 오버헤드는 제외합니다. 예를 들어 `이름` → `홍길동`은 6 + 9 = 15바이트입니다.
덮어쓸 때는 기존 크기를 빼고 새 크기를 더합니다. 모든 삭제 경로는 공통 `_delete`를 통해 집계를 갱신합니다.

SET 전에 단일 엔트리가 제한을 초과하는지 확인합니다. 초과하면 다음 오류를 반환하고 기존 값·TTL·LRU를
보존합니다(이미 만료된 데이터 정리는 수행).

```text
(error) OOM command not allowed when used_memory > 'maxmemory'
```

저장 후 전체 크기가 제한을 넘으면 LRU의 뒤에서부터 여러 키를 제거할 수 있습니다.
이때만 `evicted_keys`가 증가하며, DEL이나 TTL 만료는 포함하지 않습니다.
PDF에 구체적으로 정해지지 않은 제한 축소 정책은 **CONFIG 실행 즉시 LRU 제거**로 정했습니다.
0은 무제한이며 통계 카운터를 초기화하지 않습니다.

### 최소 힙과 TTL

`(expire_at, key)`를 최소 힙에 저장하고 `_heapify_up`, `_heapify_down`으로 순서를 복구합니다.
`peek`는 O(1)이며 가장 빠른 만료를 바로 확인할 수 있습니다. `push/pop`은 평균 O(log n)입니다.
별도의 자체 해시맵에 키의 힙 인덱스를 저장해 TTL 재설정과 임의 삭제도 평균 O(log n)에 처리합니다.
동일 키를 push하면 기존 만료 시각을 갱신합니다. 삭제된 키의 만료 항목은 힙에도 남지 않습니다.

시스템 시각 변경의 영향을 피하기 위해 `time.monotonic()`을 사용합니다.
각 저장소 명령이 시작될 때 힙 루트부터 만료된 키를 정리합니다. 유휴 상태에서 백그라운드로 정리하지는
않지만 다음 명령의 결과·키 개수·메모리 통계에는 만료된 키가 포함되지 않습니다.
만료된 키가 k개이면 정리에 평균 O(k log n)이 추가됩니다.
LRU 노드 이동 자체는 O(1)이지만 TTL이 있는 키의 실제 삭제에는 힙 제거 비용이 추가됩니다.

## 요구사항 대응

| PDF 필수 요구사항 | 구현 위치 | 검증 내용 |
| --- | --- | --- |
| 이중 연결 리스트 6개 메서드 | `linked_list.py` | 빈 리스트, 양 끝/중간 삭제, 이동, 연결 무결성 |
| 체이닝 해시맵 6개 메서드, 0.75 초과 확장 | `hash_map.py` | 강제 충돌, 경계 확장, 덮어쓰기, 삭제 |
| 최소 힙 4개 메서드 및 heapify | `min_heap.py` | 정렬 순서, 같은 만료 시각, 갱신, 임의 삭제 |
| 문자열 명령어 6개 | `store.py`, `cli.py` | 출력, 빈 값, 따옴표, 대소문자, 없는 키 |
| 메모리 명령어 2개 및 LRU | `store.py` | PDF 예시, UTF-8, 제한 축소, 다중 제거, OOM 원자성 |
| TTL 명령어 2개 및 연계 삭제 | `store.py` | 만료 경계, TTL 초기화, 재설정, 삭제 후 재생성 |
| REPL 및 오류 형식 | `cli.py` | 인자 수, 잘못된 정수, 잘못된 따옴표, 실제 프로세스 실행 |
| 내장 KV 컬렉션 금지 | 전체 구현 | AST로 dict/set/collections 및 heapq 사용 검사 |

배열 저장소와 출력 목록에는 Python `list`를 사용합니다. 리스트는 버킷/힙의 인덱스 접근과
결과 나열에 사용하고, 해시맵·LRU·힙 알고리즘을 내장 컬렉션으로 대체하지 않습니다.
범용 동적 배열, 스택/큐/덱 과제, 이진 트리/BST, Pub/Sub는 구현하지 않았습니다.
네트워크, 영속성, Redis 복잡 자료형 및 동시성 처리도 범위에 포함하지 않습니다.

## 테스트

```bash
python3 -m unittest discover -s tests -v
```

19개 테스트에 PDF 예시와 실제 CLI 프로세스 검증을 포함했습니다.
고정 시드로 힙 작업 1,500회, 저장소 혼합 작업 1,000회를 실행하며 자료구조와 메모리 집계의 일관성도 검사합니다.
TTL 테스트는 주입한 가상 시계로 실행하므로 실제 대기 시간이 필요하지 않습니다.
Python 3.13에서 실행 검증했고, Python 3.8 문법 호환성은 AST 파싱으로 확인했습니다.
EOF와 오류 이후의 정상 명령 처리도 검증합니다.
