# MyFoil API Documentation

## Overview

MyFoil provides a RESTful API for managing your Nintendo Switch library. The API is organized into several namespaces:

| Namespace | Description | Base Path |
|-----------|-------------|-----------|
| Library | Library operations and game management | `/api/v1/library` |
| TitleDB | TitleDB source management | `/api/v1/titledb` |
| Wishlist | User wishlist management | `/api/v1/wishlist` |
| Tags | Tag management | `/api/v1/tags` |
| Webhooks | Webhook configuration | `/api/v1/webhooks` |
| System | System statistics and health | `/api/v1/system` |

## Authentication

All endpoints require authentication unless specified otherwise.

### Basic Authentication
```bash
curl -X GET http://localhost:8465/api/v1/library/games \
  -H "Authorization: Basic YWRtaW46cGFzc3dvcmQ="
```

### API Key Authentication
```bash
curl -X GET http://localhost:8465/api/v1/library/games \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Rate Limiting

The API implements rate limiting. Response headers include:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Time when limit resets

---

## Library API

### List All Games

```http
GET /api/v1/library/games
```

**Authentication:** Required (shop)

**Response:**
```json
[
  {
    "id": "0100000000000001",
    "name": "Super Mario Odyssey",
    "version": "1.3.0",
    "latest_version_available": 13180,
    "size": 6420000000,
    "size_formatted": "5.98 GB",
    "has_base": true,
    "has_latest_version": false,
    "has_all_dlcs": true,
    "status_color": "yellow",
    "publisher": "Nintendo",
    "release_date": "2017-10-27",
    "description": "Explore massive 3D kingdoms...",
    "iconUrl": "https://...",
    "bannerUrl": "https://...",
    "category": ["Platformer", "Adventure"],
    "tags": ["Favorite", "Completed"],
    "region": "USA",
    "is_demo": false,
    "is_hack": false,
    "owned": true
  }
]
```

### Get Game Details

```http
GET /api/v1/library/games/{title_id}
```

**Authentication:** Required (shop)

**Parameters:**
- `title_id` (string): The game Title ID (e.g., `0100000000000001`)

### Trigger Library Scan

```http
POST /api/v1/library/scan
```

**Authentication:** Required (admin)

**Response:**
```json
{
  "success": true,
  "message": "Library scan started"
}
```

### Get Scan Status

```http
GET /api/v1/library/scan/status
```

**Authentication:** Required (shop)

**Response:**
```json
{
  "is_scanning": true,
  "is_updating_titledb": false,
  "last_scan": "2026-01-16T10:30:00",
  "files_scanned": 150,
  "files_added": 5,
  "files_removed": 0
}
```

### Delete File

```http
DELETE /api/v1/library/files/{file_id}
```

**Authentication:** Required (admin)

### List Unidentified Files

```http
GET /api/v1/library/files/unidentified
```

**Authentication:** Required (admin)

---

## TitleDB API

### List Sources

```http
GET /api/v1/titledb/sources
```

**Authentication:** Required (admin)

**Response:**
```json
[
  {
    "name": "blawar/titledb (GitHub)",
    "base_url": "https://raw.githubusercontent.com/blawar/titledb/master",
    "priority": 1,
    "enabled": true,
    "source_type": "json",
    "last_success": "2026-01-16T10:00:00",
    "last_error": null,
    "remote_date": "2026-01-16T10:00:00",
    "status": "active"
  }
]
```

### Add Source

```http
POST /api/v1/titledb/sources
```

**Authentication:** Required (admin)

**Request Body:**
```json
{
  "name": "My Custom Source",
  "base_url": "https://example.com/titledb",
  "priority": 5,
  "enabled": true,
  "source_type": "json"
}
```

### Update Source

```http
PUT /api/v1/titledb/sources/{name}
```

**Authentication:** Required (admin)

### Delete Source

```http
DELETE /api/v1/titledb/sources/{name}
```

**Authentication:** Required (admin)

### Force Update

```http
POST /api/v1/titledb/update
```

**Authentication:** Required (admin)

Forces a TitleDB update in the background.

---

## Wishlist API

### List Wishlist

```http
GET /api/v1/wishlist
```

**Authentication:** Required (shop)

**Response:**
```json
[
  {
    "id": 1,
    "title_id": "0100000000000001",
    "name": "Super Mario Odyssey",
    "priority": 1,
    "added_at": "2026-01-10T08:00:00",
    "notes": "Get on sale"
  }
]
```

### Add to Wishlist

```http
POST /api/v1/wishlist
```

**Authentication:** Required (shop)

**Request Body:**
```json
{
  "title_id": "0100000000000001",
  "priority": 2,
  "notes": "Wait for sale"
}
```

### Update Wishlist Item

```http
PUT /api/v1/wishlist/{title_id}
```

**Authentication:** Required (shop)

### Remove from Wishlist

```http
DELETE /api/v1/wishlist/{title_id}
```

**Authentication:** Required (shop)

### Export Wishlist

```http
GET /api/v1/wishlist/export?format=json|csv|html
```

**Authentication:** Required (shop)

---

## Tags API

### List Tags

```http
GET /api/v1/tags
```

**Authentication:** Required (shop)

**Response:**
```json
[
  {
    "id": 1,
    "name": "RPG",
    "color": "#FF5733",
    "game_count": 45
  }
]
```

### Create Tag

```http
POST /api/v1/tags
```

**Authentication:** Required (admin)

**Request Body:**
```json
{
  "name": "Indie",
  "color": "#33FF57"
}
```

### Update Tag

```http
PUT /api/v1/tags/{tag_id}
```

**Authentication:** Required (admin)

### Delete Tag

```http
DELETE /api/v1/tags/{tag_id}
```

**Authentication:** Required (admin)

### Get Tagged Titles

```http
GET /api/v1/tags/{tag_id}/titles
```

**Authentication:** Required (shop)

---

## Webhooks API

### List Webhooks

```http
GET /api/v1/webhooks
```

**Authentication:** Required (admin)

**Response:**
```json
[
  {
    "id": 1,
    "url": "https://example.com/webhook",
    "name": "Discord Notification",
    "events": ["library_scan", "file_added"],
    "active": true,
    "created_at": "2026-01-01T00:00:00",
    "last_triggered": "2026-01-16T10:30:00"
  }
]
```

### Create Webhook

```http
POST /api/v1/webhooks
```

**Authentication:** Required (admin)

**Request Body:**
```json
{
  "url": "https://example.com/webhook",
  "name": "My Webhook",
  "events": ["library_scan_completed", "file_added"]
}
```

### Update Webhook

```http
PUT /api/v1/webhooks/{webhook_id}
```

**Authentication:** Required (admin)

### Delete Webhook

```http
DELETE /api/v1/webhooks/{webhook_id}
```

**Authentication:** Required (admin)

### Webhook Events

| Event | Description |
|-------|-------------|
| `library_scan_started` | Library scan started |
| `library_scan_completed` | Library scan completed |
| `library_scan_failed` | Library scan failed |
| `file_added` | New file detected |
| `file_removed` | File removed |
| `titledb_update_started` | TitleDB update started |
| `titledb_update_completed` | TitleDB update completed |
| `titledb_update_failed` | TitleDB update failed |
| `system_startup` | Server started |
| `backup_created` | Backup created |

---

## System API

### Get Statistics

```http
GET /api/v1/system/stats
```

**Authentication:** Required (shop)

**Response:**
```json
{
  "total_files": 150,
  "total_games": 75,
  "total_dlcs": 120,
  "total_updates": 90,
  "unidentified_files": 5,
  "library_size": 64200000000,
  "library_size_formatted": "59.8 GB"
}
```

### Health Check

```http
GET /api/v1/system/health
```

**Authentication:** None

**Response:**
```json
{
  "status": "healthy",
  "api_version": "1.0"
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": true,
  "code": "ERROR_CODE",
  "message": "Human readable error message"
}
```

### Common Error Codes

| Code | Description |
|------|-------------|
| `UNAUTHORIZED` | Authentication required |
| `FORBIDDEN` | Insufficient permissions |
| `NOT_FOUND` | Resource not found |
| `VALIDATION_ERROR` | Invalid request data |
| `DATABASE_ERROR` | Database operation failed |
| `INTERNAL_ERROR` | Unexpected server error |

---

## Swagger UI

Interactive API documentation is available at:
```
http://localhost:8465/api/docs
```

This provides a fully interactive interface to explore and test all endpoints.
