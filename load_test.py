"""
Concurrent API load test: 20 simultaneous users hitting a POST endpoint.
Logs each user's response time and prints a summary at the end.
"""

import asyncio
import time
import statistics
from datetime import datetime, timezone

import aiohttp


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Configuration ----
API_URL = "https://postman-echo.com/post"    # <-- swap with your real endpoint
NUM_USERS = 20
REQUEST_TIMEOUT = 30                          # seconds
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    # "Authorization": "Bearer <token>",   # add if your API needs auth
}


def build_payload(user_id: int) -> dict:
    """Per-user JSON body. Customize to match your API's schema."""
    return {
        "user_id": user_id,
        "action": "load_test",
        "timestamp": _now_iso(),
        "data": {"sample": "value", "index": user_id},
    }


async def simulate_user(
    session: aiohttp.ClientSession, user_id: int
) -> dict:
    """Fire one request as 'user_id' and record timing + status."""
    payload = build_payload(user_id)
    start = time.perf_counter()
    started_at = _now_iso()

    try:
        async with session.post(
            API_URL,
            json=payload,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            # Read body so timing reflects full response, not just headers
            await resp.read()
            elapsed = time.perf_counter() - start
            print(
                f"[User {user_id:02d}] status={resp.status} "
                f"time={elapsed:.3f}s started={started_at}"
            )
            return {
                "user_id": user_id,
                "status": resp.status,
                "elapsed": elapsed,
                "ok": 200 <= resp.status < 300,
                "error": None,
            }
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - start
        print(f"[User {user_id:02d}] TIMEOUT after {elapsed:.3f}s")
        return {"user_id": user_id, "status": None, "elapsed": elapsed,
                "ok": False, "error": "timeout"}
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"[User {user_id:02d}] ERROR after {elapsed:.3f}s: {e}")
        return {"user_id": user_id, "status": None, "elapsed": elapsed,
                "ok": False, "error": str(e)}


async def run_load_test() -> list[dict]:
    # Single shared session with a connector that allows all connections
    # to open concurrently (default limit is 100, plenty for 20 users).
    connector = aiohttp.TCPConnector(limit=NUM_USERS)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [simulate_user(session, uid) for uid in range(1, NUM_USERS + 1)]
        # gather() kicks them off concurrently and waits for all to finish
        return await asyncio.gather(*tasks)


def print_summary(results: list[dict], wall_time: float) -> None:
    successful = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    times = [r["elapsed"] for r in successful]

    print("\n" + "=" * 60)
    print("LOAD TEST SUMMARY")
    print("=" * 60)
    print(f"Endpoint:         {API_URL}")
    print(f"Concurrent users: {NUM_USERS}")
    print(f"Total wall time:  {wall_time:.3f}s")
    print(f"Successful:       {len(successful)}/{NUM_USERS}")
    print(f"Failed:           {len(failed)}/{NUM_USERS}")

    if times:
        print("\nResponse times (successful requests):")
        print(f"  min:    {min(times):.3f}s")
        print(f"  max:    {max(times):.3f}s")
        print(f"  mean:   {statistics.mean(times):.3f}s")
        print(f"  median: {statistics.median(times):.3f}s")
        if len(times) > 1:
            print(f"  stdev:  {statistics.stdev(times):.3f}s")
        # p95 via sorted index
        sorted_t = sorted(times)
        p95 = sorted_t[int(len(sorted_t) * 0.95) - 1] if len(sorted_t) >= 20 else max(sorted_t)
        print(f"  p95:    {p95:.3f}s")

    if failed:
        print("\nFailures:")
        for r in failed:
            reason = r["error"] or f"HTTP {r['status']}"
            print(f"  user {r['user_id']:02d}: {reason}")
    print("=" * 60)


def main() -> None:
    print(f"Starting load test: {NUM_USERS} concurrent POSTs to {API_URL}\n")
    t0 = time.perf_counter()
    results = asyncio.run(run_load_test())
    wall_time = time.perf_counter() - t0
    print_summary(results, wall_time)


if __name__ == "__main__":
    main()
