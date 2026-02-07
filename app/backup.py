import os
import shutil
import logging
from datetime import datetime, timezone
from utils import now_utc

logger = logging.getLogger('main')

class BackupManager:
    def __init__(self, config_dir, data_dir):
        self.config_dir = config_dir
        self.data_dir = data_dir
        self.backup_dir = os.path.join(config_dir, 'backups')
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self):
        """Create a timestamped backup of database and settings"""
        timestamp = now_utc().strftime('%Y%m%d_%H%M%S')
        backup_created = False
        
        try:
            # Backup settings
            settings_path = os.path.join(self.config_dir, 'settings.yaml')
            if os.path.exists(settings_path):
                backup_settings = os.path.join(self.backup_dir, f'settings_{timestamp}.yaml')
                shutil.copy2(settings_path, backup_settings)
                logger.info(f"Settings backup created: {backup_settings}")
                backup_created = True
            
            # Backup keys if exists
            keys_path = os.path.join(self.config_dir, 'keys.txt')
            if os.path.exists(keys_path):
                backup_keys = os.path.join(self.backup_dir, f'keys_{timestamp}.txt')
                shutil.copy2(keys_path, backup_keys)
                logger.info(f"Keys backup created: {backup_keys}")
                backup_created = True
            
            if backup_created:
                self.cleanup_old_backups(keep=7)
                return True, timestamp
            else:
                logger.warning("No files to backup")
                return False, None
                
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False, None
    
    def cleanup_old_backups(self, keep=7):
        """Keep only the most recent N backups"""
        try:
            # Get all backup files grouped by type
            backup_files = {
                'db': [],
                'settings': [],
                'keys': []
            }
            
            for filename in os.listdir(self.backup_dir):
                filepath = os.path.join(self.backup_dir, filename)
                if not os.path.isfile(filepath):
                    continue
                    
                elif filename.startswith('settings_') and filename.endswith('.yaml'):
                    backup_files['settings'].append(filepath)
                elif filename.startswith('keys_') and filename.endswith('.txt'):
                    backup_files['keys'].append(filepath)
            
            # Sort by modification time and remove old ones
            for file_type, files in backup_files.items():
                files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                
                # Keep only recent N files
                for old_file in files[keep:]:
                    try:
                        os.remove(old_file)
                        logger.info(f"Removed old backup: {os.path.basename(old_file)}")
                    except Exception as e:
                        logger.error(f"Failed to remove old backup {old_file}: {e}")
                        
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def list_backups(self):
        """List all available backups"""
        backups = []
        try:
            for filename in os.listdir(self.backup_dir):
                filepath = os.path.join(self.backup_dir, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    backups.append({
                        'filename': filename,
                        'path': filepath,
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        'type': self._get_backup_type(filename)
                    })
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x['created'], reverse=True)
            return backups
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []
    
    def _get_backup_type(self, filename):
        """Determine backup file type"""
        elif filename.endswith('.json'):
            return 'settings'
        elif filename.endswith('.txt'):
            return 'keys'
        return 'unknown'
    
    def restore_backup(self, backup_filename):
        """Restore from a specific backup file"""
        try:
            backup_path = os.path.join(self.backup_dir, backup_filename)
            if not os.path.exists(backup_path):
                logger.error(f"Backup file not found: {backup_filename}")
                return False
            
            # Determine target path based on backup type
            elif backup_filename.startswith('settings_') and backup_filename.endswith('.yaml'):
                target_path = os.path.join(self.config_dir, 'settings.yaml')
            elif backup_filename.startswith('keys_') and backup_filename.endswith('.txt'):
                target_path = os.path.join(self.config_dir, 'keys.txt')
            else:
                logger.error(f"Unknown backup type: {backup_filename}")
                return False
            
            # Create safety backup of current file before restore
            if os.path.exists(target_path):
                safety_backup = f"{target_path}.pre-restore"
                shutil.copy2(target_path, safety_backup)
                logger.info(f"Created safety backup: {safety_backup}")
            
            # Restore the backup
            shutil.copy2(backup_path, target_path)
            logger.info(f"Restored {backup_filename} to {target_path}")
            return True
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False

    def delete_backup(self, filename):
        """Delete a specific backup file"""
        try:
            filepath = os.path.join(self.backup_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Backup deleted: {filename}")
                return True
            else:
                logger.error(f"Backup file not found for deletion: {filename}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete backup {filename}: {e}")
            return False
