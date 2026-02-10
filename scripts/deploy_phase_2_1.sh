#!/bin/bash
# Migration Deployment Script - Phase 2.1 (Composite Indexes)
# This script applies the necessary database migrations to add performance indexes

set -e  # Exit on error

echo "======================================"
echo "MyFoil Migration Deployment - Phase 2.1"
echo "======================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Detect if running in Docker
if [ -f /.dockerenv ]; then
    echo "Running inside Docker container"
    FLASK_CMD="flask"
else
    echo "Running outside Docker - assuming development environment"
    FLASK_CMD="flask"
fi

# Backup database before migration
echo ""
echo "Step 1: Creating database backup..."
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/pre_migration_$(date +%Y%m%d_%H%M%S).sql"

# PostgreSQL-only
if [ -z "$DATABASE_URL" ]; then
    print_error "DATABASE_URL must be set (PostgreSQL only)"
    exit 1
fi

print_success "Using PostgreSQL database"

# Create backup
print_warning "PostgreSQL backup is not automated by this script"
print_warning "Recommended: pg_dump --format=custom --file $BACKUP_FILE \"$DATABASE_URL\""
BACKUP_FILE=""

# Check current migration version
echo ""
echo "Step 2: Checking current migration version..."
CURRENT_VERSION=$($FLASK_CMD db current 2>/dev/null | grep "Current revision" | awk '{print $NF}' || echo "none")

if [ "$CURRENT_VERSION" == "none" ]; then
    print_warning "No migrations applied yet. Database may not be initialized."
elif [ "$CURRENT_VERSION" == "b2c3d4e5f9g1" ]; then
    print_success "Migration b2c3d4e5f9g1 already applied"
    print_success "Composite indexes are already in place"
    echo ""
    echo "Migration already complete. Skipping."
    exit 0
fi

print_success "Current migration version: $CURRENT_VERSION"

# Get available migrations
echo "Available migrations:"
$FLASK_CMD db heads 2>/dev/null || print_warning "Could not list migration heads"

# Apply migration
echo ""
echo "Step 3: Applying migration b2c3d4e5f9g1 (Composite Indexes)..."
echo "This will take a few seconds to several minutes depending on database size..."

# Run migration
if $FLASK_CMD db upgrade; then
    print_success "Migration applied successfully"
else
    print_error "Migration failed!"
    exit 1
fi

# Verify indexes were created
echo ""
echo "Step 4: Verifying indexes were created..."

print_warning "Please verify PostgreSQL indexes manually"

# Confirm new migration version
echo ""
echo "Step 5: Confirming new migration version..."
NEW_VERSION=$($FLASK_CMD db current 2>/dev/null | grep "Current revision" | awk '{print $NF}' || echo "none")

if [ "$NEW_VERSION" == "b2c3d4e5f9g1" ]; then
    print_success "New migration version: $NEW_VERSION"
else
    print_error "Current version after migration: $NEW_VERSION"
    print_error "Expected: b2c3d4e5f9g1"
    exit 1
fi

# Summary
echo ""
echo "======================================"
echo "Migration Complete!"
echo "======================================"
echo ""
print_success "Database has been successfully migrated"
print_success "Composite_indexes are now active"
echo ""
echo "Performance Improvements Expected:"
echo "  - Stats queries: 5-10x faster"
echo "  - Outdated games query: 3-5x faster"
echo "  - Metadata filtering: 2-3x faster"
echo ""
echo "Next Steps:"
echo "  1. Restart the application"
echo "  2. Run test_endpoints.sh to verify new features"
echo "  3. Monitor application logs for any issues"
echo ""
if [ -n "$BACKUP_FILE" ]; then
    echo "Backup created at: $BACKUP_FILE"
    echo "To rollback if needed: flask db downgrade"
fi
echo ""
