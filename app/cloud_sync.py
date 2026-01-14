import os
import json
import logging
import threading
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger('main')

# Optional dependencies
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_ENABLED = True
except ImportError:
    GOOGLE_ENABLED = False
    logger.warning("Google Drive dependencies not installed. Cloud sync will be limited.")

try:
    import dropbox
    from dropbox.files import FileMetadata, FolderMetadata
    from dropbox.exceptions import AuthError
    DROPBOX_ENABLED = True
except ImportError:
    DROPBOX_ENABLED = False
    logger.warning("Dropbox dependencies not installed. Cloud sync will be limited.")

class CloudFile:
    def __init__(self, file_id: str, name: str, size: int, modified_time: datetime, path: str):
        self.file_id = file_id
        self.name = name
        self.size = size
        self.modified_time = modified_time
        self.path = path

class CloudProvider(ABC):
    @abstractmethod
    def authenticate(self, auth_code: str = None) -> bool:
        pass

    @abstractmethod
    def list_files(self, folder_id: str = None) -> List[CloudFile]:
        pass

    @abstractmethod
    def download_file(self, file_id: str, dest_path: str) -> bool:
        pass
    
    @abstractmethod
    def get_auth_url(self) -> str:
        pass

class GoogleDriveProvider(CloudProvider):
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    
    def __init__(self, client_config: Dict, token_path: str):
        self.client_config = client_config
        self.token_path = token_path
        self.creds = None
        self.service = None
        
        if not GOOGLE_ENABLED:
            return

        self.load_credentials()

    def load_credentials(self):
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
            except Exception as e:
                logger.error(f"Failed to load Google Drive tokens: {e}")
    
    def get_auth_url(self, redirect_uri: str) -> str:
        if not GOOGLE_ENABLED: return ""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url

    def authenticate(self, auth_code: str, redirect_uri: str) -> bool:
        if not GOOGLE_ENABLED: return False
        try:
            flow = Flow.from_client_config(
                self.client_config,
                scopes=self.SCOPES,
                redirect_uri=redirect_uri
            )
            flow.fetch_token(code=auth_code)
            self.creds = flow.credentials
            
            # Save credentials
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())
            
            return True
        except Exception as e:
            logger.error(f"Google Drive authentication failed: {e}")
            return False

    def list_files(self, folder_id: str = None) -> List[CloudFile]:
        if not GOOGLE_ENABLED or not self.creds: return []
        
        try:
            if not self.creds.valid:
                if self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    return []

            service = build('drive', 'v3', credentials=self.creds)
            
            query = "trashed = false"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            
            results = service.files().list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, size, modifiedTime)"
            ).execute()
            
            items = results.get('files', [])
            files = []
            for item in items:
                # Basic filtering for game files
                if not any(item['name'].lower().endswith(ext) for ext in ['.nsp', '.nsz', '.xci', '.xcz']):
                    continue
                    
                files.append(CloudFile(
                    file_id=item['id'],
                    name=item['name'],
                    size=int(item.get('size', 0)),
                    modified_time=datetime.fromisoformat(item['modifiedTime'].replace('Z', '+00:00')),
                    path=item['name']
                ))
            return files
        except Exception as e:
            logger.error(f"Error listing Google Drive files: {e}")
            return []

    def download_file(self, file_id: str, dest_path: str) -> bool:
        # Implementation for later
        pass

class DropboxProvider(CloudProvider):
    def __init__(self, app_key: str, token_path: str):
        self.app_key = app_key
        self.token_path = token_path
        self.access_token = None
        self.refresh_token = None
        
        if not DROPBOX_ENABLED:
            return
        self.load_credentials()

    def load_credentials(self):
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token')
            except Exception as e:
                logger.error(f"Failed to load Dropbox tokens: {e}")

    def get_auth_url(self, redirect_uri: str) -> str:
        if not DROPBOX_ENABLED: return ""
        # Dropbox OAuth2 with PKCE/Refresh Tokens
        return f"https://www.dropbox.com/oauth2/authorize?client_id={self.app_key}&token_access_type=offline&response_type=code&redirect_uri={redirect_uri}"

    def authenticate(self, auth_code: str, redirect_uri: str) -> bool:
        if not DROPBOX_ENABLED: return False
        try:
            # Exchange code for token
            # Note: In a production app, we should use a proper OAuth flow handler
            import requests
            resp = requests.post('https://api.dropbox.com/oauth2/token', data={
                'code': auth_code,
                'grant_type': 'authorization_code',
                'client_id': self.app_key,
                'redirect_uri': redirect_uri
            })
            
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data['access_token']
                self.refresh_token = data.get('refresh_token')
                
                with open(self.token_path, 'w') as f:
                    json.dump({
                        'access_token': self.access_token,
                        'refresh_token': self.refresh_token
                    }, f)
                return True
            else:
                logger.error(f"Dropbox token exchange failed: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Dropbox authentication failed: {e}")
            return False

    def list_files(self, folder_id: str = None) -> List[CloudFile]:
        if not DROPBOX_ENABLED or not self.access_token: return []
        
        try:
            dbx = dropbox.Dropbox(self.access_token)
            # Simple path-based listing for Dropbox
            path = folder_id if folder_id else ""
            res = dbx.files_list_folder(path)
            
            files = []
            for entry in res.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    if not any(entry.name.lower().endswith(ext) for ext in ['.nsp', '.nsz', '.xci', '.xcz']):
                        continue
                        
                    files.append(CloudFile(
                        file_id=entry.path_lower,
                        name=entry.name,
                        size=entry.size,
                        modified_time=entry.server_modified,
                        path=entry.path_display
                    ))
            return files
        except Exception as e:
            logger.error(f"Error listing Dropbox files: {e}")
            return []

    def download_file(self, file_id: str, dest_path: str) -> bool:
        pass

class CloudManager:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.providers: Dict[str, CloudProvider] = {}
        self.tokens_dir = os.path.join(config_dir, 'tokens')
        os.makedirs(self.tokens_dir, exist_ok=True)
        
        # Initialize Google Drive if config exists
        gdrive_config = os.path.join(config_dir, 'gdrive_client_secret.json')
        if os.path.exists(gdrive_config):
            with open(gdrive_config, 'r') as f:
                config = json.load(f)
                self.providers['gdrive'] = GoogleDriveProvider(
                    config, 
                    os.path.join(self.tokens_dir, 'gdrive_token.json')
                )
        
        # Initialize Dropbox if config exists
        dropbox_config = os.path.join(config_dir, 'dropbox_app_key.txt')
        if os.path.exists(dropbox_config):
            with open(dropbox_config, 'r') as f:
                app_key = f.read().strip()
                self.providers['dropbox'] = DropboxProvider(
                    app_key,
                    os.path.join(self.tokens_dir, 'dropbox_token.json')
                )

    def get_auth_url(self, provider_name: str, redirect_uri: str) -> str:
        if provider_name in self.providers:
            return self.providers[provider_name].get_auth_url(redirect_uri)
        return ""

    def authenticate(self, provider_name: str, auth_code: str, redirect_uri: str) -> bool:
        if provider_name in self.providers:
            return self.providers[provider_name].authenticate(auth_code, redirect_uri)
        return False
        
    def list_files(self, provider_name: str, folder_id: str = None) -> List[Dict]:
        if provider_name in self.providers:
            files = self.providers[provider_name].list_files(folder_id)
            return [{
                'id': f.file_id,
                'name': f.name,
                'size': f.size,
                'modified': f.modified_time.isoformat()
            } for f in files]
        return []

# Singleton
_cloud_manager = None
def get_cloud_manager(config_dir: str = None):
    global _cloud_manager
    if _cloud_manager is None and config_dir:
        _cloud_manager = CloudManager(config_dir)
    return _cloud_manager
