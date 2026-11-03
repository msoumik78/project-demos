#!/usr/bin/env python3
"""Hold a fixed number of callers against GET /orders/{id} and print latency percentiles."""

import argparse
import http.client
import threading
import time


def percentile(sorted_values, pct):
    index = min(len(sorted_values) - 1, int(round((pct / 100) * (len(sorted_values) - 1))))
    return sorted_values[index]


def run(vus, duration, timeout):
    latencies = []
    errors = []
    lock = threading.Lock()
    stop_at = time.perf_counter() + duration

    def worker():
        local_latencies = []
        local_errors = 0
        connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=timeout)
        sequence = 0
        while time.perf_counter() < stop_at:
            started = time.perf_counter()
            try:
                connection.request("GET", f"/orders/{sequence}")
                response = connection.getresponse()
                response.read()
                elapsed_ms = (time.perf_counter() - started) * 1000
                if response.status == 200:
                    local_latencies.append(elapsed_ms)
                else:
                    local_errors += 1
            except Exception:
                local_errors += 1
                connection.close()
                connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=timeout)
            sequence += 1
        connection.close()
        with lock:
            latencies.extend(local_latencies)
            errors.append(local_errors)

    threads = [threading.Thread(target=worker) for _ in range(vus)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started

    if not latencies:
        print(f"n=0 errors={sum(errors)} rps=0 p50=nan p95=nan p99=nan max=nan")
        return None

    latencies.sort()
    print(
        f"n={len(latencies)} errors={sum(errors)} rps={len(latencies) / elapsed:.1f} "
        f"p50={percentile(latencies, 50):.1f} p95={percentile(latencies, 95):.1f} "
        f"p99={percentile(latencies, 99):.1f} max={latencies[-1]:.1f}"
    )
    return percentile(latencies, 95)


def main():
    parser = argparse.ArgumentParser(description="Load GET /orders/{id} and print percentiles.")
    parser.add_argument("--vus", type=int, default=200, help="concurrent callers")
    parser.add_argument("--duration", type=int, default=45, help="seconds to hold the load")
    parser.add_argument("--timeout", type=float, default=5, help="per-request socket timeout in seconds")
    args = parser.parse_args()
    p95 = run(args.vus, args.duration, args.timeout)
    if p95 is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
