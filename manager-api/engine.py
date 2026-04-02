import asyncio
import aiohttp
import time
from typing import Optional


async def send_single_request(session, url, method):
    start_time = time.perf_counter()
    try:
        if method.upper() == "POST":
            async with session.post(url) as response:
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                return {
                    "latency_ms": latency_ms,
                    "status_code": response.status,
                    "success": response.status < 400,
                    "start_time": start_time,
                    "end_time": end_time,
                }
        else:
            async with session.get(url) as response:
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                return {
                    "latency_ms": latency_ms,
                    "status_code": response.status,
                    "success": response.status < 400,
                    "start_time": start_time,
                    "end_time": end_time,
                }
    except Exception as e:
        end_time = time.perf_counter()
        return {
            "latency_ms": 0,
            "status_code": 0,
            "success": False,
            "error": str(e),
            "start_time": start_time,
            "end_time": end_time,
        }


async def _run_batch(session, full_url, method, total_requests, concurrency):
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_request():
        async with semaphore:
            return await send_single_request(session, full_url, method)

    tasks = [bounded_request() for _ in range(total_requests)]
    return await asyncio.gather(*tasks)


async def run_load_test(
    target_url,
    endpoint,
    method,
    total_requests,
    concurrency,
    load_profile: str = "flat",
    ramp_peak_concurrency: Optional[int] = None,
    ramp_steps: int = 5,
):
    """
    flat: fixed concurrency for all requests.
    ramp: sequential phases with increasing concurrency caps (load rises over time).
    """
    full_url = target_url.rstrip("/") + endpoint
    profile = (load_profile or "flat").lower()
    peak = int(ramp_peak_concurrency or concurrency)

    if profile != "ramp":
        connector = aiohttp.TCPConnector(limit=concurrency + 10)
        async with aiohttp.ClientSession(connector=connector) as session:
            out = await _run_batch(session, full_url, method, total_requests, concurrency)
        return list(out)

    steps = max(2, int(ramp_steps))
    base = total_requests // steps
    rem = total_requests % steps
    results = []
    connector = aiohttp.TCPConnector(limit=peak + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(steps):
            conc = max(1, int(round(peak * (i + 1) / steps)))
            n_req = base + (1 if i < rem else 0)
            if n_req <= 0:
                continue
            part = await _run_batch(session, full_url, method, n_req, conc)
            results.extend(part)
    return results


def calculate_statistics(results):
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    latencies = sorted([r["latency_ms"] for r in successful])
    total = len(results)

    if not latencies:
        return {
            "avg_latency": 0,
            "min_latency": 0,
            "max_latency": 0,
            "p50_latency": 0,
            "p99_latency": 0,
            "total_requests": total,
            "total_success": 0,
            "total_failed": total,
            "success_rate": 0.0,
            "error_rate": 100.0,
            "throughput_rps": 0.0,
        }

    n = len(latencies)
    avg_latency = sum(latencies) / n
    min_latency = latencies[0]
    max_latency = latencies[-1]
    p50_latency = latencies[int(n * 0.50)]
    p99_latency = latencies[min(int(n * 0.99), n - 1)]

    all_start = min(r["start_time"] for r in results)
    all_end = max(r["end_time"] for r in results)
    total_duration = all_end - all_start
    throughput_rps = len(successful) / total_duration if total_duration > 0 else 0

    success_rate = (len(successful) / total) * 100
    error_rate = (len(failed) / total) * 100

    return {
        "avg_latency": round(avg_latency, 2),
        "min_latency": round(min_latency, 2),
        "max_latency": round(max_latency, 2),
        "p50_latency": round(p50_latency, 2),
        "p99_latency": round(p99_latency, 2),
        "total_requests": total,
        "total_success": len(successful),
        "total_failed": len(failed),
        "success_rate": round(success_rate, 2),
        "error_rate": round(error_rate, 2),
        "throughput_rps": round(throughput_rps, 2),
    }
