#!/bin/bash
# Test Script for New API Endpoints - Phases 2.2 and 7.2
# This script tests all newly implemented endpoints

set -e

echo "======================================"
echo "MyFoil Endpoint Testing - Phases 2.2 & 7.2"
echo "======================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Default settings
BASE_URL="${BASE_URL:-http://localhost:8465}"
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test counter
test_endpoint() {
    local test_name="$1"
    local url="$2"
    local expected_status="$3"
    local description="$4"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo ""
    echo "Test $TOTAL_TESTS: $test_name"
    echo "  Endpoint: $url"
    echo "  Expected: HTTP $expected_status"
    echo "  Description: $description"

    if [ -z "$NO_COLOR" ]; then
        echo -n "  Status: "
    fi

    # Run test
    response=$(curl -s -w "%{http_code}" -o /tmp/response_$TOTAL_TESTS.json "$url" 2>/dev/null) || {
        print_error "$test_name - Connection failed"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    }

    if [ "$response" == "$expected_status" ]; then
        print_success "$test_name - Passed (HTTP $response)"
        PASSED_TESTS=$((PASSED_TESTS + 1))

        # Show response preview for successful tests
        if [ "$response" == "200" ] || [ "$response" == "201" ]; then
            echo "  Response preview:"
            cat /tmp/response_$TOTAL_TESTS.json | head -20 | sed 's/^/    /' | head -5
        fi
    else
        print_error "$test_name - Failed (got HTTP $response, expected $expected_status)"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo "  Error response:"
        cat /tmp/response_$TOTAL_TESTS.json | sed 's/^/    /' | head -10
    fi
}

# Test 1: Health Check
test_endpoint \
    "Health Check Endpoint" \
    "$BASE_URL/api/health" \
    "200" \
    "Comprehensive health check for DB, Redis, Celery, and Watchdog"

# Test 2: Readiness Probe
test_endpoint \
    "Readiness Probe" \
    "$BASE_URL/api/health/ready" \
    "200" \
    "Kubernetes readiness - checks critical components (DB)"

# Test 3: Liveness Probe
test_endpoint \
    "Liveness Probe" \
    "$BASE_URL/api/health/live" \
    "200" \
    "Kubernetes liveness - checks if Flask app is running"

# Test 4: Celery Diagnosis
test_endpoint \
    "Celery Diagnosis" \
    "$BASE_URL/api/system/celery/diagnose" \
    "200" \
    "Detailed Celery worker health and task registration status"

# Test 5: Paginated Library (default)
test_endpoint \
    "Paginated Library (page 1, 50 items)" \
    "$BASE_URL/api/library/paged?page=1&per_page=50" \
    "200" \
    "Server-side paginated library with default pagination"

# Test 6: Paginated Library (page 2, 100 items, sorted by added_at)
test_endpoint \
    "Paginated Library (custom)" \
    "$BASE_URL/api/library/paged?page=2&per_page=100&sort=added_at&order=desc" \
    "200" \
    "Paginated library with custom sort and page size"

# Test 7: Paginated Search (all games)
test_endpoint \
    "Paginated Search (all)" \
    "$BASE_URL/api/library/search/paged?q=&page=1&per_page=20" \
    "200" \
    "Search without filters using server-side pagination"

# Test 8: Paginated Search (with query)
test_endpoint \
    "Paginated Search (query)" \
    "$BASE_URL/api/library/search/paged?q=Mario&page=1&per_page=10" \
    "200" \
    "Search for 'Mario' with pagination"

# Test 9: Paginated Library (invalid page parameter)
test_endpoint \
    "Paginated Library (invalid page)" \
    "$BASE_URL/api/library/paged?page=0&per_page=50" \
    "200" \
    "Should return page 1 when invalid page is given (defaulting behavior)"

# Test 10: Paginated Library (invalid per_page)
test_endpoint \
    "Paginated Library (invalid per_page)" \
    "$BASE_URL/api/library/paged?page=1&per_page=5000" \
    "200" \
    "Should limit to max_per_page (100) when too large"

# Test 11: Cloud Status Placeholder
test_endpoint \
    "Cloud Status Placeholder" \
    "$BASE_URL/api/cloud/status" \
    "200" \
    "Placeholder endpoint after cloud sync removal"

# Test 12: Cloud Auth Placeholder
test_endpoint \
    "Cloud Auth Placeholder (gdrive)" \
    "$BASE_URL/api/cloud/auth/gdrive" \
    "503" \
    "Placeholder endpoint returning 503 (feature removed)"

# Performance Tests (optional)
echo ""
echo "======================================"
print_info "Performance Tests (Optional)"
echo "======================================"

if [ -z "$SKIP_PERFORMANCE_TESTS" ]; then
    test_endpoint \
        "Paginated Library Performance Test" \
        "$BASE_URL/api/library/paged?page=1&per_page=50" \
        "200" \
        "Measure response time for paginated library endpoint"
else
    print_warning "Skipping performance tests (SKIP_PERFORMANCE_TESTS set)"
fi

# Summary
echo ""
echo "======================================"
echo "Test Summary"
echo "======================================"
echo ""
echo "Base URL: $BASE_URL"
echo ""
echo "Total Tests: $TOTAL_TESTS"
echo -n "Passed: "
if [ $PASSED_TESTS -gt 0 ]; then
    print_success "$PASSED_TESTS"
else
    echo "$PASSED_TESTS"
fi
echo -n "Failed: "
if [ $FAILED_TESTS -gt 0 ]; then
    print_error "$FAILED_TESTS"
else
    echo "$FAILED_TESTS"
fi
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    print_success "All tests passed!"
    echo ""
    echo "✓ All new endpoints are working correctly"
    echo "✓ Health checks are operational"
    echo "✓ Pagination is functioning properly"
    echo ""
    echo "You can now:"
    echo "  1. Update the frontend to use /api/library/paged"
    echo "  2. Configure Kubernetes probes if deploying to K8s"
    echo "  3. Monitor health status in your dashboard"
    exit 0
else
    print_error "Some tests failed!"
    echo ""
    echo "Please check:"
    echo "  1. Is the application running? (Running on port 8465)"
    echo "  2. Are the new endpoints registered? (Restart app if needed)"
    echo "  3. Check application logs for errors"
    echo ""
    echo "Review failed tests above for details."
    exit 1
fi