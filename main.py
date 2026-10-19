"""프로젝트 루트에서 python3 main.py로 실행한다."""
from mini_redis.cli import main

# 터미널에서 python3 main.py로 직접 실행한 경우에만 REPL을 시작한다.
if __name__ == "__main__":
    main()
