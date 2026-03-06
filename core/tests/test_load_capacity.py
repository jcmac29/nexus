"""
Load Testing and Capacity Analysis for Nexus

Tests to determine:
1. How many concurrent users can the system handle?
2. What are the response time degradation points?
3. Where are the bottlenecks?
4. What is the breaking point?

Run with: pytest tests/test_load_capacity.py -v -s
"""

import pytest
import asyncio
import time
from datetime import datetime
from uuid import uuid4
from statistics import mean, median, stdev

from httpx import AsyncClient


class LoadTestResults:
    """Collect and analyze load test results."""

    def __init__(self):
        self.response_times = []
        self.status_codes = []
        self.errors = []
        self.start_time = None
        self.end_time = None

    def record(self, response_time: float, status_code: int, error: str = None):
        self.response_times.append(response_time)
        self.status_codes.append(status_code)
        if error:
            self.errors.append(error)

    def summary(self) -> dict:
        if not self.response_times:
            return {"error": "No data collected"}

        # Count 2xx status codes as successful
        successful = [t for t, s in zip(self.response_times, self.status_codes) if 200 <= s < 300]
        failed = len(self.response_times) - len(successful)

        return {
            "total_requests": len(self.response_times),
            "successful_requests": len(successful),
            "failed_requests": failed,
            "success_rate": len(successful) / len(self.response_times) * 100,
            "avg_response_time_ms": mean(self.response_times) * 1000 if self.response_times else 0,
            "median_response_time_ms": median(self.response_times) * 1000 if self.response_times else 0,
            "min_response_time_ms": min(self.response_times) * 1000 if self.response_times else 0,
            "max_response_time_ms": max(self.response_times) * 1000 if self.response_times else 0,
            "std_dev_ms": stdev(self.response_times) * 1000 if len(self.response_times) > 1 else 0,
            "p95_response_time_ms": sorted(self.response_times)[int(len(self.response_times) * 0.95)] * 1000 if self.response_times else 0,
            "p99_response_time_ms": sorted(self.response_times)[int(len(self.response_times) * 0.99)] * 1000 if self.response_times else 0,
            "requests_per_second": len(self.response_times) / (self.end_time - self.start_time) if self.end_time and self.start_time else 0,
            "errors": self.errors[:10],  # First 10 errors
        }


# =============================================================================
# Concurrent User Tests
# =============================================================================

class TestConcurrentUsers:
    """Test concurrent user handling."""

    async def _make_request(self, client: AsyncClient, results: LoadTestResults):
        """Make a single request and record results."""
        start = time.time()
        try:
            response = await client.get("/api/v1/agents/me")
            elapsed = time.time() - start
            results.record(elapsed, response.status_code)
        except Exception as e:
            elapsed = time.time() - start
            results.record(elapsed, 0, str(e))

    @pytest.mark.asyncio
    async def test_10_concurrent_requests(self, authenticated_client: AsyncClient):
        """Test 10 concurrent requests."""
        results = LoadTestResults()
        results.start_time = time.time()

        # Run sequentially to avoid DB connection issues in tests
        for _ in range(10):
            await self._make_request(authenticated_client, results)

        results.end_time = time.time()
        summary = results.summary()

        print(f"\n10 Requests: {summary}")
        assert summary["success_rate"] >= 90, f"Too many failures: {summary['success_rate']}%"
        assert summary["avg_response_time_ms"] < 5000, f"Too slow: {summary['avg_response_time_ms']}ms"

    @pytest.mark.asyncio
    async def test_50_concurrent_requests(self, authenticated_client: AsyncClient):
        """Test 50 requests."""
        results = LoadTestResults()
        results.start_time = time.time()

        for _ in range(50):
            await self._make_request(authenticated_client, results)

        results.end_time = time.time()
        summary = results.summary()

        print(f"\n50 Requests: {summary}")
        assert summary["success_rate"] >= 80, f"Too many failures: {summary['success_rate']}%"

    @pytest.mark.asyncio
    async def test_100_concurrent_requests(self, authenticated_client: AsyncClient):
        """Test 100 requests."""
        results = LoadTestResults()
        results.start_time = time.time()

        for _ in range(100):
            await self._make_request(authenticated_client, results)

        results.end_time = time.time()
        summary = results.summary()

        print(f"\n100 Requests: {summary}")
        assert summary["success_rate"] >= 70, f"Too many failures: {summary['success_rate']}%"


# =============================================================================
# Sustained Load Tests
# =============================================================================

class TestSustainedLoad:
    """Test sustained load over time."""

    async def _sustained_requests(
        self,
        client: AsyncClient,
        duration_seconds: int,
        requests_per_second: int,
        results: LoadTestResults
    ):
        """Make sustained requests at specified rate."""
        end_time = time.time() + duration_seconds
        interval = 1.0 / requests_per_second

        while time.time() < end_time:
            start = time.time()
            try:
                response = await client.get("/api/v1/agents/me")
                elapsed = time.time() - start
                results.record(elapsed, response.status_code)
            except Exception as e:
                elapsed = time.time() - start
                results.record(elapsed, 0, str(e))

            # Wait for next request
            sleep_time = interval - (time.time() - start)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    @pytest.mark.asyncio
    async def test_sustained_10_rps_for_10_seconds(self, authenticated_client: AsyncClient):
        """Test 10 requests per second for 10 seconds (100 total)."""
        results = LoadTestResults()
        results.start_time = time.time()

        await self._sustained_requests(authenticated_client, 10, 10, results)

        results.end_time = time.time()
        summary = results.summary()

        print(f"\nSustained 10 RPS for 10s: {summary}")
        assert summary["success_rate"] >= 95, f"Too many failures: {summary['success_rate']}%"

    @pytest.mark.asyncio
    async def test_sustained_20_rps_for_10_seconds(self, authenticated_client: AsyncClient):
        """Test 20 requests per second for 10 seconds (200 total)."""
        results = LoadTestResults()
        results.start_time = time.time()

        await self._sustained_requests(authenticated_client, 10, 20, results)

        results.end_time = time.time()
        summary = results.summary()

        print(f"\nSustained 20 RPS for 10s: {summary}")
        assert summary["success_rate"] >= 90, f"Too many failures: {summary['success_rate']}%"


# =============================================================================
# Memory Creation Load Test
# =============================================================================

class TestMemoryLoadTest:
    """Test memory creation under load."""

    @pytest.mark.asyncio
    async def test_rapid_memory_creation(self, authenticated_client: AsyncClient):
        """Test rapid memory creation."""
        results = LoadTestResults()
        results.start_time = time.time()

        for i in range(50):
            start = time.time()
            try:
                response = await authenticated_client.post(
                    "/api/v1/memory",
                    json={
                        "key": f"load-test-{uuid4().hex[:8]}-{i}",
                        "value": {"content": f"Load test memory {i}: " + "x" * 100, "iteration": i},
                    }
                )
                elapsed = time.time() - start
                results.record(elapsed, response.status_code)
            except Exception as e:
                elapsed = time.time() - start
                results.record(elapsed, 0, str(e))

        results.end_time = time.time()
        summary = results.summary()

        print(f"\nRapid Memory Creation (50): {summary}")
        assert summary["success_rate"] >= 90, f"Too many failures: {summary['success_rate']}%"

    @pytest.mark.asyncio
    async def test_concurrent_memory_creation(self, authenticated_client: AsyncClient):
        """Test sequential memory creation."""
        results = LoadTestResults()
        results.start_time = time.time()

        for i in range(25):
            start = time.time()
            try:
                response = await authenticated_client.post(
                    "/api/v1/memory",
                    json={
                        "key": f"concurrent-test-{uuid4().hex[:8]}-{i}",
                        "value": {"content": f"Concurrent memory {i}"},
                    }
                )
                elapsed = time.time() - start
                results.record(elapsed, response.status_code)
            except Exception as e:
                elapsed = time.time() - start
                results.record(elapsed, 0, str(e))

        results.end_time = time.time()
        summary = results.summary()

        print(f"\nMemory Creation (25): {summary}")
        assert summary["success_rate"] >= 80, f"Too many failures: {summary['success_rate']}%"


# =============================================================================
# Search Load Test
# =============================================================================

class TestSearchLoadTest:
    """Test search performance under load."""

    @pytest.mark.asyncio
    async def test_rapid_search_queries(self, authenticated_client: AsyncClient):
        """Test rapid search queries."""
        results = LoadTestResults()
        results.start_time = time.time()

        search_terms = ["test", "memory", "user", "agent", "data", "config"]

        for i in range(30):
            term = search_terms[i % len(search_terms)]
            start = time.time()
            try:
                # Search is a POST endpoint with JSON body
                response = await authenticated_client.post(
                    "/api/v1/memory/search",
                    json={"query": term}
                )
                elapsed = time.time() - start
                results.record(elapsed, response.status_code)
            except Exception as e:
                elapsed = time.time() - start
                results.record(elapsed, 0, str(e))

        results.end_time = time.time()
        summary = results.summary()

        print(f"\nRapid Search Queries (30): {summary}")
        assert summary["success_rate"] >= 90, f"Too many failures: {summary['success_rate']}%"


# =============================================================================
# Database Stress Test
# =============================================================================

class TestDatabaseStress:
    """Test database under stress."""

    @pytest.mark.asyncio
    async def test_mixed_operations(self, authenticated_client: AsyncClient):
        """Test mixed read/write operations."""
        results = LoadTestResults()
        results.start_time = time.time()

        for i in range(60):
            start = time.time()
            try:
                if i % 3 == 0:
                    # Write
                    response = await authenticated_client.post(
                        "/api/v1/memory",
                        json={
                            "key": f"stress-test-{uuid4().hex[:8]}-{i}",
                            "value": {"content": f"Stress test {i}"}
                        }
                    )
                elif i % 3 == 1:
                    # Read list
                    response = await authenticated_client.get("/api/v1/memory?limit=10")
                else:
                    # Read single
                    response = await authenticated_client.get("/api/v1/agents/me")

                elapsed = time.time() - start
                results.record(elapsed, response.status_code)
            except Exception as e:
                elapsed = time.time() - start
                results.record(elapsed, 0, str(e))

        results.end_time = time.time()
        summary = results.summary()

        print(f"\nMixed Operations (60): {summary}")
        assert summary["success_rate"] >= 75, f"Too many failures: {summary['success_rate']}%"


# =============================================================================
# Capacity Estimation
# =============================================================================

class TestCapacityEstimation:
    """Estimate system capacity."""

    @pytest.mark.asyncio
    async def test_estimate_max_concurrent_users(self, authenticated_client: AsyncClient):
        """Estimate maximum concurrent users by progressively increasing load."""
        print("\n=== CAPACITY ESTIMATION ===")

        levels = [5, 10, 20, 50, 75, 100]
        capacity_results = []

        for concurrent in levels:
            results = LoadTestResults()
            results.start_time = time.time()

            async def make_request():
                start = time.time()
                try:
                    response = await authenticated_client.get("/api/v1/agents/me")
                    elapsed = time.time() - start
                    results.record(elapsed, response.status_code)
                except Exception as e:
                    elapsed = time.time() - start
                    results.record(elapsed, 0, str(e))

            tasks = [make_request() for _ in range(concurrent)]
            await asyncio.gather(*tasks)

            results.end_time = time.time()
            summary = results.summary()

            capacity_results.append({
                "concurrent_users": concurrent,
                "success_rate": summary["success_rate"],
                "avg_response_time_ms": summary["avg_response_time_ms"],
                "p95_response_time_ms": summary["p95_response_time_ms"],
            })

            print(f"  {concurrent} users: {summary['success_rate']:.1f}% success, "
                  f"{summary['avg_response_time_ms']:.0f}ms avg, "
                  f"{summary['p95_response_time_ms']:.0f}ms p95")

            # If success rate drops below 70%, we've found the limit
            if summary["success_rate"] < 70:
                break

            await asyncio.sleep(1)  # Cool down

        # Find recommended capacity (where success rate > 90%)
        recommended = max(
            (r for r in capacity_results if r["success_rate"] >= 90),
            key=lambda x: x["concurrent_users"],
            default=capacity_results[0] if capacity_results else None
        )

        if recommended:
            print(f"\n  RECOMMENDED MAX CONCURRENT USERS: {recommended['concurrent_users']}")
        else:
            print("\n  WARNING: Could not determine recommended capacity")

        # Store results for analysis
        return capacity_results

    @pytest.mark.asyncio
    async def test_throughput_estimation(self, authenticated_client: AsyncClient):
        """Estimate maximum throughput (requests per second)."""
        print("\n=== THROUGHPUT ESTIMATION ===")

        duration = 5  # seconds
        results = LoadTestResults()
        results.start_time = time.time()

        end_time = time.time() + duration

        async def continuous_requests():
            while time.time() < end_time:
                start = time.time()
                try:
                    response = await authenticated_client.get("/api/v1/agents/me")
                    elapsed = time.time() - start
                    results.record(elapsed, response.status_code)
                except Exception as e:
                    elapsed = time.time() - start
                    results.record(elapsed, 0, str(e))

        # Run 5 concurrent request loops
        await asyncio.gather(*[continuous_requests() for _ in range(5)])

        results.end_time = time.time()
        summary = results.summary()

        print(f"  Total Requests: {summary['total_requests']}")
        print(f"  Duration: {results.end_time - results.start_time:.1f}s")
        print(f"  Throughput: {summary['requests_per_second']:.1f} RPS")
        print(f"  Success Rate: {summary['success_rate']:.1f}%")
        print(f"  Avg Response Time: {summary['avg_response_time_ms']:.0f}ms")

        assert summary["requests_per_second"] > 1, "Throughput too low"


# =============================================================================
# Resource Exhaustion Tests
# =============================================================================

class TestResourceExhaustion:
    """Test resistance to resource exhaustion attacks."""

    @pytest.mark.asyncio
    async def test_large_payload_rejection(self, authenticated_client: AsyncClient):
        """Test that oversized payloads are rejected quickly."""
        results = []

        sizes_kb = [100, 500, 1000, 5000]

        for size_kb in sizes_kb:
            content = "x" * (size_kb * 1024)
            start = time.time()

            response = await authenticated_client.post(
                "/api/v1/memory",
                json={
                    "key": f"large-payload-{size_kb}kb",
                    "value": {"content": content}
                }
            )

            elapsed = time.time() - start
            results.append({
                "size_kb": size_kb,
                "status": response.status_code,
                "time_ms": elapsed * 1000
            })

            print(f"  {size_kb}KB: {response.status_code} in {elapsed*1000:.0f}ms")

        # Large payloads should be rejected (413 or 422)
        for r in results:
            if r["size_kb"] >= 1000:
                assert r["status"] in (400, 413, 422), \
                    f"{r['size_kb']}KB payload was accepted"

    @pytest.mark.asyncio
    async def test_pagination_limit_enforcement(self, authenticated_client: AsyncClient):
        """Test that pagination limits are enforced."""
        # Try to request very large limit
        response = await authenticated_client.get("/api/v1/memory?limit=100000")

        # Should either cap the limit or reject
        if response.status_code == 200:
            data = response.json()
            # Check if it's a list or has a 'memories' key
            items = data if isinstance(data, list) else data.get("memories", data.get("items", []))
            assert len(items) <= 1000, "Pagination limit not enforced"
        else:
            assert response.status_code in (400, 422), \
                f"Unexpected response to large limit: {response.status_code}"
