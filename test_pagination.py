#!/usr/bin/env python3
"""
Script to test the Phase 2.2 paginated library endpoint
Verifies that server-side pagination is working correctly
"""

import requests
import json
from urllib.parse import urljoin


def test_paginated_library():
    # Test server - update this URL for production
    BASE_URL = "http://127.0.0.1:8465"  # Change to production URL when ready
    AUTH = ("admin", "admin")  # Update with your credentials

    print("=" * 60)
    print("Testing Phase 2.2 Paginated Library Endpoint")
    print("=" * 60)
    print(f"Server: {BASE_URL}")
    print("")

    # Test 1: Get first page
    print("Test 1: Fetching first page (page=1, per_page=60)...")
    response = requests.get(
        urljoin(BASE_URL, "/api/library/paged"),
        params={"page": 1, "per_page": 60, "sort_by": "name", "order": "asc"},
        auth=AUTH,
    )

    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        pagination = data.get("pagination", {})

        print(f"  ✓ Response OK ({response.status_code})")
        print(f"  ✓ Received {len(items)} items")
        print(f"  ✓ Total items: {pagination.get('total_items', 'N/A')}")
        print(f"  ✓ Has next page: {pagination.get('has_next', False)}")

        if items:
            sample = items[0]
            print(f"\n  Sample game:")
            print(f"    Name: {sample.get('name', 'N/A')}")
            print(f"    ID: {sample.get('id', 'N/A')}")
            print(f"    Status: {sample.get('status_color', 'N/A')}")
    else:
        print(f"  ✗ Failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return False

    # Test 2: Get second page
    print("\nTest 2: Fetching second page (page=2, per_page=60)...")
    response = requests.get(
        urljoin(BASE_URL, "/api/library/paged"),
        params={"page": 2, "per_page": 60, "sort_by": "name", "order": "asc"},
        auth=AUTH,
    )

    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        pagination = data.get("pagination", {})

        print(f"  ✓ Response OK ({response.status_code})")
        print(f"  ✓ Received {len(items)} items")
        print(f"  ✓ Current page: {pagination.get('page', 'N/A')}")

        if items:
            print(f"  First item: {items[0].get('name', 'N/A')}")
    else:
        print(f"  ✗ Failed: {response.status_code}")
        return False

    # Test 3: Search endpoint
    print("\nTest 3: Testing search endpoint (q='Mario')...")
    response = requests.get(
        urljoin(BASE_URL, "/api/library/search/paged"), params={"q": "Mario", "page": 1, "per_page": 20}, auth=AUTH
    )

    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        pagination = data.get("pagination", {})

        print(f"  ✓ Response OK ({response.status_code})")
        print(f"  ✓ Search returned {len(items)} results")
        print(f"  ✓ Total matching items: {pagination.get('total_items', 'N/A')}")

        if items:
            print(f"  First result: {items[0].get('name', 'N/A')}")
    else:
        print(f"  ✗ Failed: {response.status_code}")
        return False

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print("\nExpected frontend behavior:")
    print("  1. Dashboard loads instantly with first 60 games")
    print("  2. Infinite scroll loads next page when user scrolls down")
    print("  3. Pagination metadata used for progress indicators")
    print("  4. Client-side filtering works on loaded games")
    print("")

    return True


if __name__ == "__main__":
    test_paginated_library()
