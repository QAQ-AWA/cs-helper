"""下载阶段的并发：串行下载五个 300MB 的 demo 要十几分钟。"""

import time

import pipeline


def test_workers_run_in_parallel():
    seen: list[int] = []

    def handler(item):
        time.sleep(0.15)
        seen.append(item)

    started = time.monotonic()
    pipeline._run_download_workers(list(range(6)), handler, 3)
    elapsed = time.monotonic() - started

    assert sorted(seen) == list(range(6))
    # 串行要 0.9s，三路并发应在 0.3-0.6s 之间。
    assert elapsed < 0.75, elapsed


def test_single_worker_stays_sequential():
    seen: list[int] = []

    def handler(item):
        seen.append(item)

    pipeline._run_download_workers([1, 2, 3], handler, 1)
    assert seen == [1, 2, 3]
