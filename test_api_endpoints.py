#!/usr/bin/env python3
"""
Test script to verify Phase 2.2 (Pagination) and Phase 7.2 (Health Check) endpoints.
This script tests the endpoints created during optimization.
"""

import sys
import os
import requests
import json
from datetime import datetime

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def log(message, color=None):
    """Print colored message"""
    if color:
        print(f"{color}{message}{RESET}")
    else:
        print(message)


def test_endpoint(name, url, method="GET", data=None, expected_status=200, auth_token=None):
    """Test a single API endpoint"""
    log(f"\n{'=' * 80}")
    log(f"Testing: {name}", BLUE)
    log(f"URL: {url}")
    log(f"Method: {method}")
    log(f"Expected Status: {expected_status}")

    try:
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=10)
        else:
            log(f"Unsupported method: {method}", RED)
            return False

        log(f"Status Code: {response.status_code}")

        if response.status_code == expected_status:
            log(f"✓ PASS - Status code matches expected", GREEN)
            try:
                json_data = response.json()
                log(f"Response (first 500 chars): {json.dumps(json_data, indent=2)[:500]}")
            except:
                log(f"Response (first 200 chars): {response.text[:200]}")
            return True
        else:
            log(f"✗ FAIL - Status code mismatch", RED)
            log(f"Response: {response.text[:500]}")
            return False

    except requests.exceptions.ConnectionError:
        log(f"✗ FAIL - Connection refused (server not running)", RED)
        return False
    except requests.exceptions.Timeout:
        log(f"✗ FAIL - Request timeout", RED)
        return False
    except Exception as e:
        log(f"✗ FAIL - {str(e)}", RED)
        return False


def main():
    """Main test runner"""
    print("=" * 80)
    print("MyFoil API Endpoint Tests")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 80)

    # Prompt for base URL
    base_url = input("\nEnter base URL (default: http://localhost:5000): ").strip()
    if not base_url:
        base_url = "http://localhost:5000"

    log(f"\nBase URL: {base_url}", BLUE)

    # Prompt for auth token (optional)
    auth_token = input("Enter auth token (press Enter to skip): ").strip()
    if auth_token:
        log(f"Auth token provided", BLUE)
    else:
        log(f"No auth token - some endpoints may fail", YELLOW)

    # Test Phase 7.2: Health Check Endpoints
    log("\n" + "=" * 80, BLUE)
    log("PHASE 7.2: Health Check Endpoints", BLUE)
    log("=" * 80)

    results = []

    results.append(
        test_endpoint("Health Check (GET /api/health)", f"{base_url}/api/health", method="GET", expected_status=200)
    )

    results.append(
        test_endpoint(
            "Health Check (GET /api/health/ready)", f"{base_url}/api/health/ready", method="GET", expected_status=200
        )
    )

    results.append(
        test_endpoint(
            "Health Check (GET /api/health/live)", f"{base_url}/api/health/live", method="GET", expected_status=200
        )
    )

    # Test Phase 2.2: Pagination Endpoints
    log("\n" + "=" * 80, BLUE)
    log("PHASE 2.2: Server-Side Pagination Endpoints", BLUE)
    log("=" * 80)

    results.append(
        test_endpoint(
            "Pagination (GET /api/library/paged)",
            f"{base_url}/api/library/paged?page=1&per_page=10&sort=name&order=asc",
            method="GET",
            expected_status=200 if auth_token else 401,  # Requires auth
        )
    )

    results.append(
        test_endpoint(
            "Pagination Search (GET /api/library/search/paged)",
            f"{base_url}/api/library/search/paged?q=test&page=1&per_page=10",
            method="GET",
            expected_status=200 if auth_token else 401,  # Requires auth
        )
    )

    # Test System Info
    log("\n" + "=" * 80, BLUE)
    log("System Information", BLUE)
    log("=" * 80)

    results.append(
        test_endpoint(
            "System Info (GET /api/system/info)",
            f"{base_url}/api/system/info",
            method="GET",
            expected_status=200,  # Usually public
        )
    )

    # Test Migration Status (requires admin)
    log("\n" + "=" * 80, BLUE)
    log("Database Migration Endpoints (Phase 2.1)", BLUE)
    log("=" * 80)

    results.append(
        test_endpoint(
            "Migration Status (GET /api/system/migrate/status)",
            f"{base_url}/api/system/migrate/status",
            method="GET",
            expected_status=200 if auth_token else 401,  # Requires auth
        )
    )

    # Test Celery Workers (requires admin)
    log("\n" + "=" * 80, BLUE)
    log("Celery Worker Endpoints", BLUE)
    log("=" * 80)

    results.append(
        test_endpoint(
            "Celery Test (POST /api/system/celery/test)",
            f"{base_url}/api/system/celery/test",
            method="POST",
            expected_status=200 if auth_token else 401,  # Requires auth
        )
    )

    # Summary
    log("\n" + "=" * 80, BLUE)
    log("TEST SUMMARY", BLUE)
    log("=" * 80)

    passed = sum(results)
    total = len(results)
    failed = total - passed

    log(f"\nTotal Tests: {total}")
    log(f"Passed: {passed}", GREEN)
    log(f"Failed: {failed}", RED if failed > 0 else "")
    log(f"Success Rate: {(passed / total) * 100:.1f}%", GREEN if passed == total else YELLOW)

    if passed == total:
        log("\n✓ All tests passed!", GREEN)
        return 0
    else:
        log("\n✗ Some tests failed. Check the output above for details.", RED)
        return 1


if __name__ == "__main__":
    sys.exit(main())
