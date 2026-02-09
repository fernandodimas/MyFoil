#!/usr/bin/env python3
"""
Analyze slow queries in MyFoil for Phase 2.3 optimization.
This script identifies potential N+1 queries, missing indexes, and inefficient joins.
"""

import sys
import os
import re

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))


SLOW_QUERY_PATTERNS = {
    "N+1 Query": [
        r'\.query\(.*\)\.first\(\)\s*#?[^"\']*for\s+.*in\s+.*:',  # Query inside loop
        r'\.filter\(.*\)\.all\(\)\s*#?[^"\']*for\s+.*in\s+.*:',  # Query inside loop
        r'for\s+\w+\s+in\s+\w+#?[^"\']*\.\w+\(\):',  # Method call inside loop
    ],
    "Missing Index Hints": [
        r"\.filter_by\([^)]*\)",  # filter_by without index hint
        r"\.filter\([^)]*\)",  # Complex filter without index
    ],
    "Large Scans": [
        r'\.query\(.*\)\.all\(\)\s*#?[^"\']*(?!limit)',  # query().all() without limit
    ],
    "InefficientJoins": [
        r"\.join\(.*\).*\.join\(.*\)",  # Multiple potential joins
    ],
}


def analyze_file(filepath):
    """Analyze a Python file for slow query patterns"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    issues = []

    for pattern_name, patterns in SLOW_QUERY_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                context = lines[max(0, line_num - 3) : line_num + 2]
                issues.append(
                    {"file": filepath, "line": line_num, "type": pattern_name, "pattern": pattern, "context": context}
                )

    return issues


def find_query_files():
    """Find Python files that likely contain database queries"""
    files_to_check = []

    for root, dirs, files in os.walk("app"):
        skip_dirs = {"__pycache__", "migrations", "static", "templates"}
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                # Skip very small files
                if os.path.getsize(filepath) > 1000:
                    files_to_check.append(filepath)

    return files_to_check


def analyze_library_routes():
    """Specific analysis of routes/library.py for optimization opportunities"""
    Library_issues = []

    with open("app/routes/library.py", "r", encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    # Check for stats queries (lines 383-404 in original analysis)
    stats_pattern = r'@library_bp\.route\(["\'].*stats.*["\']'
    if re.search(stats_pattern, content):
        Library_issues.append(
            {
                "file": "app/routes/library.py",
                "type": "Stats Query",
                "description": "Multiple COUNT queries - should use composite indexes",
                "recommendation": "Apply Phase 2.1 migration (b2c3d4e5f9g1)",
            }
        )

    # Check for outdated games query (line 298)
    outdated_pattern = r"(up_to_date\s*==\s*False|have_base\s*==\s*True)"
    if re.search(outdated_pattern, content):
        Library_issues.append(
            {
                "file": "app/routes/library.py",
                "type": "Outdated Games Query",
                "description": "Filter on up_to_date and have_base columns",
                "recommendation": "Use idx_titles_up_to_date_have_base index",
            }
        )

    return Library_issues


def main():
    """Main analysis function"""
    print("=" * 80)
    print("PHASE 2.3: Slow Query Analysis")
    print("=" * 80)
    print("\nScanning for potential performance issues...\n")

    # Analyze all Python files
    files_to_check = find_query_files()
    all_issues = []

    for filepath in files_to_check:
        issues = analyze_file(filepath)
        if issues:
            all_issues.extend(issues)

    # Specific analysis for library routes
    library_issues = analyze_library_routes()
    all_issues.extend(library_issues)

    if not all_issues:
        print("✓ No obvious performance issues found in code patterns.")
        return

    # Group by type
    by_type = {}
    for issue in all_issues:
        issue_type = issue["type"]
        if issue_type not in by_type:
            by_type[issue_type] = []
        by_type[issue_type].append(issue)

    # Print recommendations
    print(f"Found {len(all_issues)} potential optimization opportunities:\n")

    for issue_type, issues in sorted(by_type.items()):
        print(f"\n{'=' * 80}")
        print(f"{issue_type} ({len(issues)} occurrences)")
        print(f"{'=' * 80}")

        for issue in issues[:5]:  # Show first 5 for each type
            print(f"\n  File: {issue['file']}")
            if "line" in issue:
                print(f"  Line: {issue['line']}")
            if "description" in issue:
                print(f"  Description: {issue['description']}")
            if "recommendation" in issue:
                print(f"  Recommendation: {issue['recommendation']}")
            if "context" in issue:
                print(f"  Context:")
                for ctx_line in issue["context"]:
                    print(f"    {ctx_line}")

        if len(issues) > 5:
            print(f"\n  ... and {len(issues) - 5} more {issue_type.lower()} occurrences")

    print("\n" + "=" * 80)
    print("RECOMMENDED ACTIONS (Priority Order):")
    print("=" * 80)
    print("\n1. IMMEDIATE - Apply Phase 2.1 Migration:")
    print("   python apply_phase_2_1_migration.py")
    print("   (or use /api/system/migrate endpoint)")
    print("\n2. HIGH - Test queries with EXPLAIN ANALYZE:")
    print("   - Stats queries in routes/library.py")
    print("   - Outdated games query")
    print("   - File listing with identification")
    print("\n3. MEDIUM - Add query result caching (Redis/Memcached)")
    print("4. LOW - Implement query batching for N+1 issues")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
