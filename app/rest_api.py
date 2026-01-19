from flask_restx import Api, Resource, fields
import logging
from auth import access_required

logger = logging.getLogger("main")


def init_rest_api(app):
    api = Api(
        app,
        version="1.0",
        title="MyFoil API",
        description="Nintendo Switch Library Manager API",
        doc="/api/docs",
        authorizations={
            "basic": {"type": "basic", "description": "Basic authentication with admin credentials"},
            "bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "API key authentication",
            },
        },
    )

    # Namespaces
    ns_library = api.namespace("v1/library", description="Library operations")
    ns_titledb = api.namespace("v1/titledb", description="TitleDB operations")
    ns_system = api.namespace("v1/system", description="System operations")
    ns_wishlist = api.namespace("v1/wishlist", description="Wishlist operations")
    ns_tags = api.namespace("v1/tags", description="Tag operations")
    ns_webhooks = api.namespace("v1/webhooks", description="Webhook operations")

    # Models
    game_model = api.model(
        "Game",
        {
            "id": fields.String(required=True, description="Title ID (e.g., 0100000000000001)"),
            "name": fields.String(required=True, description="Game name"),
            "version": fields.String(description="Current installed version"),
            "latest_version_available": fields.Integer(description="Latest version available in TitleDB"),
            "size": fields.Integer(description="Total size in bytes"),
            "size_formatted": fields.String(description="Human readable size"),
            "has_base": fields.Boolean(description="Has base game"),
            "has_latest_version": fields.Boolean(description="Is up to date"),
            "has_all_dlcs": fields.Boolean(description="Has all DLCs"),
            "status_color": fields.String(description="Status color for UI (green/yellow/red)"),
            "publisher": fields.String(description="Publisher/Developer"),
            "release_date": fields.String(description="Release date (YYYY-MM-DD)"),
            "description": fields.String(description="Game description"),
            "iconUrl": fields.String(description="Icon URL"),
            "bannerUrl": fields.String(description="Banner URL"),
            "category": fields.List(fields.String, description="Categories/Genres"),
            "tags": fields.List(fields.String, description="Custom tags"),
            "region": fields.String(description="Region code (USA/EUR/JPN)"),
            "is_demo": fields.Boolean(description="Is a demo version"),
            "is_hack": fields.Boolean(description="Is a hack/modification"),
            "owned": fields.Boolean(description="Is owned by user"),
            "added_at": fields.String(description="Date added to library"),
            "screenshots": fields.List(fields.String, description="Screenshot URLs"),
        },
    )

    file_model = api.model(
        "File",
        {
            "id": fields.Integer(description="File unique ID"),
            "filename": fields.String(description="File name"),
            "filepath": fields.String(description="Full path on disk"),
            "size": fields.Integer(description="Size in bytes"),
            "size_formatted": fields.String(description="Human readable size"),
            "extension": fields.String(description="File extension (.nsp/.nsz/.xci/.xcz)"),
            "identified": fields.Boolean(description="Has been identified"),
            "app_id": fields.String(description="App ID within the title"),
            "sha256": fields.String(description="SHA256 hash"),
        },
    )

    unidentified_file_model = api.model(
        "UnidentifiedFile",
        {
            "id": fields.Integer(description="File ID"),
            "filename": fields.String(description="Filename"),
            "filepath": fields.String(description="Path"),
            "size_formatted": fields.String(description="Size"),
            "error": fields.String(description="Identification error message"),
        },
    )

    source_model = api.model(
        "TitleDBSource",
        {
            "name": fields.String(description="Source name"),
            "base_url": fields.String(description="Base URL or path"),
            "priority": fields.Integer(description="Priority (lower = higher priority)"),
            "enabled": fields.Boolean(description="Is enabled"),
            "source_type": fields.String(description="Type of source (json/folder/zip_legacy)"),
            "last_success": fields.String(description="Last successful update timestamp"),
            "last_error": fields.String(description="Last error message"),
            "remote_date": fields.String(description="Remote file last modified date"),
            "status": fields.String(description="Current status (active/error/disabled)"),
        },
    )

    wishlist_item_model = api.model(
        "WishlistItem",
        {
            "id": fields.Integer(description="Wishlist item ID"),
            "title_id": fields.String(required=True, description="Title ID"),
            "name": fields.String(description="Game name"),
            "priority": fields.Integer(description="Priority (1=high, 5=low)"),
            "added_at": fields.String(description="Date added"),
            "notes": fields.String(description="User notes"),
        },
    )

    tag_model = api.model(
        "Tag",
        {
            "id": fields.Integer(description="Tag ID"),
            "name": fields.String(required=True, description="Tag name"),
            "color": fields.String(description="Tag color (hex code)"),
            "game_count": fields.Integer(description="Number of games with this tag"),
        },
    )

    webhook_model = api.model(
        "Webhook",
        {
            "id": fields.Integer(description="Webhook ID"),
            "url": fields.String(required=True, description="Webhook URL"),
            "name": fields.String(description="Webhook name"),
            "events": fields.List(fields.String, description="Events to trigger on"),
            "active": fields.Boolean(description="Is active"),
            "created_at": fields.String(description="Creation date"),
            "last_triggered": fields.String(description="Last triggered date"),
        },
    )

    stats_model = api.model(
        "Stats",
        {
            "total_files": fields.Integer(description="Total files in library"),
            "total_games": fields.Integer(description="Total games owned"),
            "total_dlcs": fields.Integer(description="Total DLCs owned"),
            "total_updates": fields.Integer(description="Total updates owned"),
            "unidentified_files": fields.Integer(description="Files that could not be identified"),
            "library_size": fields.Integer(description="Total library size in bytes"),
            "library_size_formatted": fields.String(description="Human readable library size"),
        },
    )

    scan_status_model = api.model(
        "ScanStatus",
        {
            "is_scanning": fields.Boolean(description="Is a scan currently running"),
            "is_updating_titledb": fields.Boolean(description="Is TitleDB update running"),
            "last_scan": fields.String(description="Last scan timestamp"),
            "files_scanned": fields.Integer(description="Files scanned in last scan"),
            "files_added": fields.Integer(description="New files added"),
            "files_removed": fields.Integer(description="Files removed"),
        },
    )

    error_model = api.model(
        "Error",
        {
            "error": fields.Boolean(description="Error occurred"),
            "code": fields.String(description="Error code"),
            "message": fields.String(description="Error message"),
        },
    )

    # Namespace Library
    @ns_library.route("/games")
    class GameList(Resource):
        @ns_library.doc("list_games")
        @access_required("shop")
        @ns_library.marshal_list_with(game_model)
        def get(self):
            """List all games in library"""
            from library import generate_library

            return generate_library()

    @ns_library.route("/games/<string:title_id>")
    @ns_library.response(404, "Game not found")
    @ns_library.param("title_id", "The game Title ID")
    class GameInfo(Resource):
        @ns_library.doc("get_game")
        @access_required("shop")
        def get(self, title_id):
            """Get game details with updates and DLCs"""
            from app import app_info_api

            # Reuse existing logic that returns JSON
            return app_info_api(title_id)

    @ns_library.route("/scan")
    class LibraryScan(Resource):
        @ns_library.doc("start_scan")
        @access_required("admin")
        def post(self):
            """Trigger a library scan (Async if Celery enabled)"""
            from app import scan_library_api

            return scan_library_api()

    @ns_library.route("/scan/status")
    class LibraryScanStatus(Resource):
        @ns_library.doc("get_scan_status")
        @access_required("shop")
        def get(self):
            """Get current scan and update status"""
            from app import process_status_api

            return process_status_api()

    @ns_library.route("/files/<int:file_id>")
    @ns_library.response(404, "File not found")
    class FileResource(Resource):
        @ns_library.doc("delete_file")
        @access_required("admin")
        def delete(self, file_id):
            """Delete a file from disk and database"""
            from app import delete_file_api

            return delete_file_api(file_id)

    @ns_library.route("/files/unidentified")
    class UnidentifiedFiles(Resource):
        @ns_library.doc("list_unidentified")
        @access_required("admin")
        @ns_library.marshal_list_with(unidentified_file_model)
        def get(self):
            """List all unidentified files"""
            from app import get_unidentified_files_api

            return get_unidentified_files_api().get_json()

    # Namespace TitleDB
    @ns_titledb.route("/sources")
    class SourceList(Resource):
        @ns_titledb.doc("list_sources")
        @access_required("admin")
        @ns_titledb.marshal_list_with(source_model)
        def get(self):
            """List all TitleDB sources"""
            import titledb

            return titledb.get_titledb_sources_status()

        @ns_titledb.doc("add_source")
        @access_required("admin")
        def post(self):
            """Add a new TitleDB source"""
            from app import titledb_sources_api

            return titledb_sources_api()

    @ns_titledb.route("/sources/<string:name>")
    @ns_titledb.param("name", "The source name")
    class Source(Resource):
        @ns_titledb.doc("update_source")
        @access_required("admin")
        def put(self, name):
            """Update an existing TitleDB source"""
            from app import titledb_sources_api

            # Fake request body for direct call if needed or just use current request
            return titledb_sources_api()

        @ns_titledb.doc("delete_source")
        @access_required("admin")
        def delete(self, name):
            """Remove a TitleDB source"""
            from app import titledb_sources_api

            return titledb_sources_api()

    @ns_titledb.route("/update")
    class TitleDBUpdate(Resource):
        @ns_titledb.doc("force_update")
        @access_required("admin")
        def post(self):
            """Force TitleDB update in background"""
            from app import force_titledb_update_api

            return force_titledb_update_api()

    # Namespace System
    @ns_system.route("/stats")
    class Stats(Resource):
        @access_required("shop")
        def get(self):
            """Get general repository statistics"""
            from db import Files, Apps
            from constants import APP_TYPE_BASE, APP_TYPE_DLC, APP_TYPE_UPD

            return {
                "total_files": Files.query.count(),
                "total_games": Apps.query.filter_by(app_type=APP_TYPE_BASE, owned=True).count(),
                "total_dlcs": Apps.query.filter_by(app_type=APP_TYPE_DLC, owned=True).count(),
                "total_updates": Apps.query.filter_by(app_type=APP_TYPE_UPD, owned=True).count(),
                "unidentified_files": Files.query.filter(Files.app_id == None).count(),
            }

    @ns_system.route("/health")
    class Health(Resource):
        def get(self):
            """Simple health check endpoint"""
            return {"status": "healthy", "api_version": "1.0"}

    # Namespace Wishlist
    @ns_wishlist.route("")
    class Wishlist(Resource):
        @ns_wishlist.doc("list_wishlist")
        @access_required("shop")
        @ns_wishlist.marshal_list_with(wishlist_item_model)
        def get(self):
            """Get user's wishlist"""
            from routes.wishlist import get_wishlist_api

            return get_wishlist_api()

        @ns_wishlist.doc("add_to_wishlist")
        @access_required("shop")
        def post(self):
            """Add a game to wishlist"""
            from routes.wishlist import add_to_wishlist_api

            return add_to_wishlist_api()

    @ns_wishlist.route("/<string:title_id>")
    @ns_wishlist.param("title_id", "The game Title ID")
    class WishlistItem(Resource):
        @ns_wishlist.doc("update_wishlist_priority")
        @access_required("shop")
        def put(self, title_id):
            """Update wishlist item priority"""
            from routes.wishlist import update_wishlist_item_api

            return update_wishlist_item_api(title_id)

        @ns_wishlist.doc("remove_from_wishlist")
        @access_required("shop")
        def delete(self, title_id):
            """Remove a game from wishlist"""
            from routes.wishlist import remove_from_wishlist_api

            return remove_from_wishlist_api(title_id)

    @ns_wishlist.route("/export")
    class WishlistExport(Resource):
        @ns_wishlist.doc("export_wishlist")
        @access_required("shop")
        def get(self):
            """Export wishlist in various formats"""
            from routes.wishlist import export_wishlist_api

            return export_wishlist_api()

    # Namespace Tags
    @ns_tags.route("")
    class TagList(Resource):
        @ns_tags.doc("list_tags")
        @access_required("shop")
        @ns_tags.marshal_list_with(tag_model)
        def get(self):
            """Get all tags"""
            from routes.library import get_tags_api

            return get_tags_api()

        @ns_tags.doc("create_tag")
        @access_required("admin")
        def post(self):
            """Create a new tag"""
            from routes.library import create_tag_api

            return create_tag_api()

    @ns_tags.route("/<int:tag_id>")
    @ns_tags.param("tag_id", "The tag ID")
    class Tag(Resource):
        @ns_tags.doc("update_tag")
        @access_required("admin")
        def put(self, tag_id):
            """Update a tag"""
            from routes.library import update_tag_api

            return update_tag_api(tag_id)

        @ns_tags.doc("delete_tag")
        @access_required("admin")
        def delete(self, tag_id):
            """Delete a tag"""
            from routes.library import delete_tag_api

            return delete_tag_api(tag_id)

    @ns_tags.route("/<int:tag_id>/titles")
    @ns_tags.param("tag_id", "The tag ID")
    class TagTitles(Resource):
        @ns_tags.doc("get_tagged_titles")
        @access_required("shop")
        @ns_tags.marshal_list_with(game_model)
        def get(self, tag_id):
            """Get all titles with a specific tag"""
            from routes.library import get_titles_by_tag_api

            return get_titles_by_tag_api(tag_id)

    # Namespace Webhooks
    @ns_webhooks.route("")
    class WebhookList(Resource):
        @ns_webhooks.doc("list_webhooks")
        @access_required("admin")
        @ns_webhooks.marshal_list_with(webhook_model)
        def get(self):
            """Get all webhooks"""
            from routes.settings import get_webhooks_api

            return get_webhooks_api()

        @ns_webhooks.doc("create_webhook")
        @access_required("admin")
        def post(self):
            """Create a new webhook"""
            from routes.settings import create_webhook_api

            return create_webhook_api()

    @ns_webhooks.route("/<int:webhook_id>")
    @ns_webhooks.param("webhook_id", "The webhook ID")
    class Webhook(Resource):
        @ns_webhooks.doc("update_webhook")
        @access_required("admin")
        def put(self, webhook_id):
            """Update a webhook"""
            from routes.settings import update_webhook_api

            return update_webhook_api(webhook_id)

        @ns_webhooks.doc("delete_webhook")
        @access_required("admin")
        def delete(self, webhook_id):
            """Delete a webhook"""
            from routes.settings import delete_webhook_api

            return delete_webhook_api(webhook_id)

    return api
