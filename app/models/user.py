"""
Model: User
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(255))
    admin_access = db.Column(db.Boolean)
    shop_access = db.Column(db.Boolean)
    backup_access = db.Column(db.Boolean)

    @property
    def is_admin(self):
        return self.admin_access

    def has_shop_access(self):
        return self.shop_access

    def has_backup_access(self):
        return self.backup_access

    def has_admin_access(self):
        return self.admin_access

    def has_access(self, access):
        if access == "admin":
            return self.has_admin_access()
        elif access == "shop":
            return self.has_shop_access()
        elif access == "backup":
            return self.has_backup_access()



