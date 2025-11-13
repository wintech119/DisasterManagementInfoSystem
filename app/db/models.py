"""
SQLAlchemy models for DRIMS
Maps to existing database schema (no auto-create)
"""
from app.db import db
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import CheckConstraint

class User(UserMixin, db.Model):
    """User authentication model with MFA and lockout support"""
    __tablename__ = 'user'
    
    user_id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    username = db.Column(db.String(60), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    password_algo = db.Column(db.String(20), nullable=False, default='argon2id')
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    full_name = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    organization = db.Column(db.String(200))
    job_title = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    timezone = db.Column(db.String(50), nullable=False, default='America/Jamaica')
    language = db.Column(db.String(10), nullable=False, default='en')
    notification_preferences = db.Column(db.Text)
    assigned_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'))
    last_login_at = db.Column(db.DateTime)
    create_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    update_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    mfa_enabled = db.Column(db.Boolean, nullable=False, default=False)
    mfa_secret = db.Column(db.String(64))
    failed_login_count = db.Column(db.SmallInteger, nullable=False, default=0)
    lock_until_at = db.Column(db.DateTime)
    password_changed_at = db.Column(db.DateTime)
    
    agency_id = db.Column(db.Integer, db.ForeignKey('agency.agency_id'))
    status_code = db.Column(db.CHAR(1), nullable=False, default='A')
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    roles = db.relationship('Role', 
                           secondary='user_role', 
                           primaryjoin='User.user_id==UserRole.user_id',
                           secondaryjoin='Role.id==UserRole.role_id',
                           back_populates='users')
    warehouses = db.relationship('Warehouse', 
                                secondary='user_warehouse', 
                                primaryjoin='User.user_id==UserWarehouse.user_id',
                                secondaryjoin='Warehouse.warehouse_id==UserWarehouse.warehouse_id',
                                back_populates='users')
    agency = db.relationship('Agency', foreign_keys=[agency_id], backref='users')
    
    def get_id(self):
        """Override UserMixin get_id to use user_id instead of id"""
        return str(self.user_id)

class Role(db.Model):
    """Role definitions for RBAC"""
    __tablename__ = 'role'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    users = db.relationship('User', 
                           secondary='user_role',
                           primaryjoin='Role.id==UserRole.role_id',
                           secondaryjoin='User.user_id==UserRole.user_id',
                           back_populates='roles')

class UserRole(db.Model):
    """User-Role assignment (many-to-many)"""
    __tablename__ = 'user_role'
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), primary_key=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.user_id'))
    create_by_id = db.Column(db.String(20), nullable=False, default='system')
    create_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    update_by_id = db.Column(db.String(20), nullable=False, default='system')
    update_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class Permission(db.Model):
    """Permission definitions for RBAC"""
    __tablename__ = 'permission'
    
    perm_id = db.Column(db.Integer, primary_key=True)
    resource = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class RolePermission(db.Model):
    """Role-Permission assignment (many-to-many)"""
    __tablename__ = 'role_permission'
    
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), primary_key=True)
    perm_id = db.Column(db.Integer, db.ForeignKey('permission.perm_id'), primary_key=True)
    scope_json = db.Column(db.JSON)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class UserWarehouse(db.Model):
    """User-Warehouse access control"""
    __tablename__ = 'user_warehouse'
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'), primary_key=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.user_id'))

class Event(db.Model):
    """Disaster Event (from aidmgmt-3.sql)"""
    __tablename__ = 'event'
    
    event_id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(16), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    event_name = db.Column(db.String(60), nullable=False)
    event_desc = db.Column(db.String(255), nullable=False)
    impact_desc = db.Column(db.Text, nullable=False)
    status_code = db.Column(db.CHAR(1), nullable=False)
    closed_date = db.Column(db.Date)
    reason_desc = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class Custodian(db.Model):
    """GOJ Agency (ODPEM)"""
    __tablename__ = 'custodian'
    
    custodian_id = db.Column(db.Integer, primary_key=True)
    custodian_name = db.Column(db.String(120), nullable=False)
    address1_text = db.Column(db.String(255), nullable=False)
    address2_text = db.Column(db.String(255))
    parish_code = db.Column(db.CHAR(2), db.ForeignKey('parish.parish_code'), nullable=False)
    contact_name = db.Column(db.String(50), nullable=False)
    phone_no = db.Column(db.String(20), nullable=False)
    email_text = db.Column(db.String(100))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class Warehouse(db.Model):
    """Warehouse/Storage Location (from aidmgmt-3.sql)"""
    __tablename__ = 'warehouse'
    
    warehouse_id = db.Column(db.Integer, primary_key=True)
    warehouse_name = db.Column(db.Text, nullable=False)
    warehouse_type = db.Column(db.String(10), nullable=False)
    address1_text = db.Column(db.String(255), nullable=False)
    address2_text = db.Column(db.String(255))
    parish_code = db.Column(db.CHAR(2), db.ForeignKey('parish.parish_code'), nullable=False)
    contact_name = db.Column(db.String(50), nullable=False)
    phone_no = db.Column(db.String(20), nullable=False)
    email_text = db.Column(db.String(100))
    custodian_id = db.Column(db.Integer, db.ForeignKey('custodian.custodian_id'), nullable=False)
    status_code = db.Column(db.CHAR(1), nullable=False)
    reason_desc = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    parish = db.relationship('Parish', backref='warehouses')
    custodian = db.relationship('Custodian', backref='warehouses')
    users = db.relationship('User', 
                           secondary='user_warehouse',
                           primaryjoin='Warehouse.warehouse_id==UserWarehouse.warehouse_id',
                           secondaryjoin='User.user_id==UserWarehouse.user_id',
                           back_populates='warehouses')

class Agency(db.Model):
    """Agency (Request-only locations)"""
    __tablename__ = 'agency'
    
    agency_id = db.Column(db.Integer, primary_key=True)
    agency_name = db.Column(db.String(120), nullable=False, unique=True)
    agency_type = db.Column(db.String(16), nullable=False)
    address1_text = db.Column(db.String(255), nullable=False)
    address2_text = db.Column(db.String(255))
    parish_code = db.Column(db.CHAR(2), db.ForeignKey('parish.parish_code'), nullable=False)
    contact_name = db.Column(db.String(50), nullable=False)
    phone_no = db.Column(db.String(20), nullable=False)
    email_text = db.Column(db.String(100))
    ineligible_event_id = db.Column(db.Integer, db.ForeignKey('event.event_id'))
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    parish = db.relationship('Parish', backref='agencies')
    ineligible_event = db.relationship('Event', backref='ineligible_agencies')
    warehouse = db.relationship('Warehouse', backref='agency', uselist=False)

class Parish(db.Model):
    """Jamaican Parish"""
    __tablename__ = 'parish'
    
    parish_code = db.Column(db.CHAR(2), primary_key=True)
    parish_name = db.Column(db.String(40), nullable=False)

class UnitOfMeasure(db.Model):
    """Unit of Measure"""
    __tablename__ = 'unitofmeasure'
    
    uom_code = db.Column(db.String(25), primary_key=True)
    uom_desc = db.Column(db.String(60), nullable=False)
    comments_text = db.Column(db.Text)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class ItemCategory(db.Model):
    """Item Category"""
    __tablename__ = 'itemcatg'
    
    category_code = db.Column(db.String(30), primary_key=True)
    category_desc = db.Column(db.String(60), nullable=False)
    comments_text = db.Column(db.Text)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class Item(db.Model):
    """Relief Item (from aidmgmt-3.sql)"""
    __tablename__ = 'item'
    
    item_id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(60), nullable=False, unique=True)
    sku_code = db.Column(db.String(30), nullable=False, unique=True)
    category_code = db.Column(db.String(30), db.ForeignKey('itemcatg.category_code'), nullable=False)
    item_desc = db.Column(db.Text, nullable=False)
    reorder_qty = db.Column(db.Numeric(12, 2), nullable=False)
    default_uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    usage_desc = db.Column(db.Text)
    storage_desc = db.Column(db.Text)
    expiration_apply_flag = db.Column(db.Boolean, nullable=False)
    comments_text = db.Column(db.Text)
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    category = db.relationship('ItemCategory', backref='items')
    default_uom = db.relationship('UnitOfMeasure', backref='items')

class Inventory(db.Model):
    """Inventory (from aidmgmt-3.sql)"""
    __tablename__ = 'inventory'
    
    inventory_id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), nullable=False)
    usable_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    reserved_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    defective_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expired_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    last_verified_by = db.Column(db.String(20))
    last_verified_date = db.Column(db.Date)
    status_code = db.Column(db.CHAR(1), nullable=False)
    comments_text = db.Column(db.Text)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    warehouse = db.relationship('Warehouse', backref='inventories')
    item = db.relationship('Item', backref='inventories')
    uom = db.relationship('UnitOfMeasure', backref='inventories')

class Donor(db.Model):
    """Donor"""
    __tablename__ = 'donor'
    
    donor_id = db.Column(db.Integer, primary_key=True)
    donor_type = db.Column(db.CHAR(1), nullable=False)
    donor_name = db.Column(db.String(255), nullable=False, unique=True)
    org_type_desc = db.Column(db.String(30))
    address1_text = db.Column(db.String(255), nullable=False)
    address2_text = db.Column(db.String(255))
    country_id = db.Column(db.SmallInteger, default=388)
    phone_no = db.Column(db.String(20), nullable=False)
    email_text = db.Column(db.String(100))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)

class Donation(db.Model):
    """Donation"""
    __tablename__ = 'donation'
    
    donation_id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donor.donor_id'), nullable=False)
    donation_desc = db.Column(db.Text, nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.event_id'), nullable=False)
    custodian_id = db.Column(db.Integer, db.ForeignKey('custodian.custodian_id'), nullable=False)
    received_date = db.Column(db.Date, nullable=False)
    status_code = db.Column(db.CHAR(1), nullable=False)
    comments_text = db.Column(db.Text)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    verify_by_id = db.Column(db.String(20), nullable=False)
    verify_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    donor = db.relationship('Donor', backref='donations')
    event = db.relationship('Event', backref='donations')
    custodian = db.relationship('Custodian', backref='donations')

class ReliefRqstStatus(db.Model):
    """Relief Request Status Lookup Table"""
    __tablename__ = 'reliefrqst_status'
    
    status_code = db.Column(db.SmallInteger, primary_key=True)
    status_desc = db.Column(db.String(20), nullable=False)
    reason_rqrd_flag = db.Column(db.Boolean, nullable=False, default=False)
    is_active_flag = db.Column(db.Boolean, nullable=False, default=True)

class ReliefRqst(db.Model):
    """Relief Request / Needs List (AIDMGMT workflow)"""
    __tablename__ = 'reliefrqst'
    
    reliefrqst_id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, db.ForeignKey('agency.agency_id'), nullable=False)
    request_date = db.Column(db.Date, nullable=False)
    tracking_no = db.Column(db.String(7), nullable=False)
    eligible_event_id = db.Column(db.Integer, db.ForeignKey('event.event_id'))
    urgency_ind = db.Column(db.CHAR(1), nullable=False)
    rqst_notes_text = db.Column(db.Text)
    review_notes_text = db.Column(db.Text)
    status_code = db.Column(db.SmallInteger, db.ForeignKey('reliefrqst_status.status_code'), nullable=False, default=0)
    status_reason_desc = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    review_by_id = db.Column(db.String(20))
    review_dtime = db.Column(db.DateTime)
    action_by_id = db.Column(db.String(20))
    action_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    agency = db.relationship('Agency', backref='relief_requests')
    eligible_event = db.relationship('Event', backref='eligible_relief_requests')
    status = db.relationship('ReliefRqstStatus', backref='relief_requests')

class ReliefRqstItem(db.Model):
    """Relief Request Item"""
    __tablename__ = 'reliefrqst_item'
    
    reliefrqst_id = db.Column(db.Integer, db.ForeignKey('reliefrqst.reliefrqst_id'), primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    request_qty = db.Column(db.Numeric(12, 2), nullable=False)
    issue_qty = db.Column(db.Numeric(12, 2), nullable=False)
    urgency_ind = db.Column(db.CHAR(1), nullable=False)
    rqst_reason_desc = db.Column(db.String(255))
    required_by_date = db.Column(db.Date)
    status_code = db.Column(db.CHAR(1), nullable=False, server_default='R')
    status_reason_desc = db.Column(db.String(255))
    action_by_id = db.Column(db.String(20))
    action_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    relief_request = db.relationship('ReliefRqst', backref='items')
    item = db.relationship('Item', backref='request_items')

class ReliefPkg(db.Model):
    """Relief Package / Fulfilment (AIDMGMT workflow)"""
    __tablename__ = 'reliefpkg'
    
    reliefpkg_id = db.Column(db.Integer, primary_key=True)
    to_inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), nullable=False)
    reliefrqst_id = db.Column(db.Integer, db.ForeignKey('reliefrqst.reliefrqst_id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    dispatch_dtime = db.Column(db.DateTime)
    transport_mode = db.Column(db.String(255))
    comments_text = db.Column(db.String(255))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime)
    verify_by_id = db.Column(db.String(20), nullable=False)
    verify_dtime = db.Column(db.DateTime)
    received_by_id = db.Column(db.String(20), nullable=False)
    received_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    relief_request = db.relationship('ReliefRqst', backref='packages')
    to_inventory = db.relationship('Inventory', backref='relief_packages')

class ReliefPkgItem(db.Model):
    """Relief Package Item"""
    __tablename__ = 'reliefpkg_item'
    __table_args__ = (
        db.ForeignKeyConstraint(
            ['fr_inventory_id', 'item_id'],
            ['inventory.inventory_id', 'inventory.item_id']
        ),
    )
    
    reliefpkg_id = db.Column(db.Integer, db.ForeignKey('reliefpkg.reliefpkg_id'), primary_key=True)
    fr_inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    item_qty = db.Column(db.Numeric(12, 2), nullable=False)
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    reason_text = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    package = db.relationship('ReliefPkg', backref='items')
    item = db.relationship('Item', backref='package_items')
    from_inventory = db.relationship('Inventory', foreign_keys=[fr_inventory_id, item_id])

class DBIntake(db.Model):
    """Distribution/Donation Intake (AIDMGMT workflow step 3)"""
    __tablename__ = 'dbintake'
    
    reliefpkg_id = db.Column(db.Integer, db.ForeignKey('reliefpkg.reliefpkg_id'), primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), primary_key=True)
    intake_date = db.Column(db.Date, nullable=False)
    comments_text = db.Column(db.String(255))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime)
    verify_by_id = db.Column(db.String(20))
    verify_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    package = db.relationship('ReliefPkg', backref='intake_records')
    inventory = db.relationship('Inventory', backref='intake_records')

class DBIntakeItem(db.Model):
    """Distribution/Donation Intake Item"""
    __tablename__ = 'dbintake_item'
    __table_args__ = (
        db.ForeignKeyConstraint(
            ['reliefpkg_id', 'inventory_id'],
            ['dbintake.reliefpkg_id', 'dbintake.inventory_id']
        ),
    )
    
    reliefpkg_id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    usable_qty = db.Column(db.Numeric(12, 2), nullable=False)
    location1_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    defective_qty = db.Column(db.Numeric(12, 2), nullable=False)
    location2_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    expired_qty = db.Column(db.Numeric(12, 2), nullable=False)
    location3_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    status_code = db.Column(db.CHAR(1), nullable=False)
    comments_text = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    item = db.relationship('Item', backref='intake_items')

class DistributionPackage(db.Model):
    """DRIMS Distribution Package (Alternative workflow)"""
    __tablename__ = 'distribution_package'
    
    id = db.Column(db.Integer, primary_key=True)
    package_number = db.Column(db.String(64), unique=True, nullable=False)
    recipient_agency_id = db.Column(db.Integer, db.ForeignKey('agency.agency_id'), nullable=False)
    assigned_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.event_id'))
    status = db.Column(db.String(50), default='Draft', nullable=False)
    is_partial = db.Column(db.Boolean, default=False, nullable=False)
    created_by = db.Column(db.String(200), nullable=False)
    approved_by = db.Column(db.String(200))
    approved_at = db.Column(db.DateTime)
    dispatched_by = db.Column(db.String(200))
    dispatched_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    
    agency = db.relationship('Agency', backref='distribution_packages')
    warehouse = db.relationship('Warehouse', backref='distribution_packages')
    event = db.relationship('Event', backref='distribution_packages')

class DistributionPackageItem(db.Model):
    """DRIMS Distribution Package Item"""
    __tablename__ = 'distribution_package_item'
    
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('distribution_package.id', ondelete='CASCADE'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.Text)
    
    package = db.relationship('DistributionPackage', backref='items')
    item = db.relationship('Item', backref='distribution_package_items')

class Transfer(db.Model):
    """Transfer between warehouses"""
    __tablename__ = 'transfer'
    
    transfer_id = db.Column(db.Integer, primary_key=True)
    fr_inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), nullable=False)
    to_inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), nullable=False)
    transfer_date = db.Column(db.Date, nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.event_id'))
    reason_text = db.Column(db.String(255))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    verify_by_id = db.Column(db.String(20), nullable=False)
    verify_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    from_inventory = db.relationship('Inventory', foreign_keys=[fr_inventory_id])
    to_inventory = db.relationship('Inventory', foreign_keys=[to_inventory_id])
    event = db.relationship('Event', backref='transfers')

class TransferItem(db.Model):
    """Transfer item details"""
    __tablename__ = 'transfer_item'
    
    transfer_id = db.Column(db.Integer, db.ForeignKey('transfer.transfer_id'), primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    item_qty = db.Column(db.Numeric(12,2), nullable=False)
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    reason_text = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    transfer = db.relationship('Transfer', backref='items')
    item = db.relationship('Item')
    unit_of_measure = db.relationship('UnitOfMeasure')

class TransferRequest(db.Model):
    """Transfer request workflow (DRIMS extension)"""
    __tablename__ = 'transfer_request'
    
    id = db.Column(db.Integer, primary_key=True)
    from_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'), nullable=False)
    to_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), nullable=False)
    quantity = db.Column(db.Numeric(12,2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='PENDING')
    requested_by = db.Column(db.Integer, db.ForeignKey('user.user_id'))
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.user_id'))
    reviewed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    
    from_warehouse = db.relationship('Warehouse', foreign_keys=[from_warehouse_id])
    to_warehouse = db.relationship('Warehouse', foreign_keys=[to_warehouse_id])
    item = db.relationship('Item')
    requester = db.relationship('User', foreign_keys=[requested_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

class Location(db.Model):
    """Warehouse bin/shelf locations"""
    __tablename__ = 'location'
    
    location_id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), nullable=False)
    aisle_no = db.Column(db.String(20))
    bin_no = db.Column(db.String(20))
    qty = db.Column(db.Numeric(15,4), nullable=False, default=0)
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    warehouse = db.relationship('Warehouse', backref='locations')
    item = db.relationship('Item', backref='locations')

class ItemLocation(db.Model):
    """Item locations within inventory - tracks items at specific bin/shelf locations (AIDMGMT)"""
    __tablename__ = 'item_location'
    
    inventory_id = db.Column(db.Integer, primary_key=True, nullable=False)
    item_id = db.Column(db.Integer, primary_key=True, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.location_id'), primary_key=True, nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    
    __table_args__ = (
        db.ForeignKeyConstraint(['item_id', 'inventory_id'], ['inventory.item_id', 'inventory.inventory_id']),
    )
    
    location = db.relationship('Location', backref='item_locations')

class DonationIntake(db.Model):
    """Donation intake - receiving donations into warehouse inventory (AIDMGMT)"""
    __tablename__ = 'dnintake'
    
    donation_id = db.Column(db.Integer, db.ForeignKey('donation.donation_id'), primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), primary_key=True)
    intake_date = db.Column(db.Date, nullable=False)
    comments_text = db.Column(db.String(255))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime)
    verify_by_id = db.Column(db.String(20), nullable=False)
    verify_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    donation = db.relationship('Donation', backref='intakes')
    inventory = db.relationship('Inventory', backref='donation_intakes')

class DonationIntakeItem(db.Model):
    """Items in donation intake (AIDMGMT)"""
    __tablename__ = 'dnintake_item'
    
    donation_id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    usable_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location1_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    defective_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location2_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    expired_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location3_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    status_code = db.Column(db.CHAR(1), nullable=False)
    comments_text = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    __table_args__ = (
        db.ForeignKeyConstraint(['donation_id', 'inventory_id'], ['dnintake.donation_id', 'dnintake.inventory_id']),
    )
    
    item = db.relationship('Item', backref='donation_intake_items')
    unit_of_measure = db.relationship('UnitOfMeasure')

class TransferIntake(db.Model):
    """Transfer intake - receiving transfers at destination warehouse (AIDMGMT)"""
    __tablename__ = 'xfintake'
    
    transfer_id = db.Column(db.Integer, db.ForeignKey('transfer.transfer_id'), primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), primary_key=True)
    intake_date = db.Column(db.Date, nullable=False)
    comments_text = db.Column(db.String(255))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime)
    verify_by_id = db.Column(db.String(20), nullable=False)
    verify_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    transfer = db.relationship('Transfer', backref='intakes')
    inventory = db.relationship('Inventory', backref='transfer_intakes')

class TransferIntakeItem(db.Model):
    """Items in transfer intake (AIDMGMT)"""
    __tablename__ = 'xfintake_item'
    
    transfer_id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    usable_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location1_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    defective_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location2_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    expired_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location3_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    status_code = db.Column(db.CHAR(1), nullable=False)
    comments_text = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    __table_args__ = (
        db.ForeignKeyConstraint(['transfer_id', 'inventory_id'], ['xfintake.transfer_id', 'xfintake.inventory_id']),
    )
    
    item = db.relationship('Item', backref='transfer_intake_items')
    unit_of_measure = db.relationship('UnitOfMeasure')

class TransferReturn(db.Model):
    """Transfer returns - items being returned from destination to source warehouse (AIDMGMT)"""
    __tablename__ = 'xfreturn'
    
    xfreturn_id = db.Column(db.Integer, primary_key=True)
    fr_inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), nullable=False)
    to_inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), nullable=False)
    return_date = db.Column(db.Date, nullable=False)
    reason_text = db.Column(db.String(255))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime)
    verify_by_id = db.Column(db.String(20), nullable=False)
    verify_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    from_inventory = db.relationship('Inventory', foreign_keys=[fr_inventory_id], backref='returns_sent')
    to_inventory = db.relationship('Inventory', foreign_keys=[to_inventory_id], backref='returns_received')

class TransferReturnItem(db.Model):
    """Items in transfer return (AIDMGMT)"""
    __tablename__ = 'xfreturn_item'
    
    xfreturn_id = db.Column(db.Integer, db.ForeignKey('xfreturn.xfreturn_id'), primary_key=True)
    inventory_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    usable_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    defective_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    expired_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    reason_text = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    __table_args__ = (
        db.ForeignKeyConstraint(['item_id', 'inventory_id'], ['inventory.item_id', 'inventory.inventory_id']),
    )
    
    transfer_return = db.relationship('TransferReturn', backref='items')
    item = db.relationship('Item', backref='transfer_return_items')
    unit_of_measure = db.relationship('UnitOfMeasure')

class ReturnIntake(db.Model):
    """Return intake - receiving returned items at source warehouse (AIDMGMT)"""
    __tablename__ = 'rtintake'
    
    xfreturn_id = db.Column(db.Integer, db.ForeignKey('xfreturn.xfreturn_id'), primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.inventory_id'), primary_key=True)
    intake_date = db.Column(db.Date, nullable=False)
    comments_text = db.Column(db.String(255))
    status_code = db.Column(db.CHAR(1), nullable=False)
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime)
    verify_by_id = db.Column(db.String(20), nullable=False)
    verify_dtime = db.Column(db.DateTime)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    transfer_return = db.relationship('TransferReturn', backref='intakes')
    inventory = db.relationship('Inventory', backref='return_intakes')

class ReturnIntakeItem(db.Model):
    """Items in return intake (AIDMGMT)"""
    __tablename__ = 'rtintake_item'
    
    xfreturn_id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), primary_key=True)
    usable_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location1_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    defective_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location2_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    expired_qty = db.Column(db.DECIMAL(12, 2), nullable=False)
    location3_id = db.Column(db.Integer, db.ForeignKey('location.location_id'))
    uom_code = db.Column(db.String(25), db.ForeignKey('unitofmeasure.uom_code'), nullable=False)
    status_code = db.Column(db.CHAR(1), nullable=False)
    comments_text = db.Column(db.String(255))
    create_by_id = db.Column(db.String(20), nullable=False)
    create_dtime = db.Column(db.DateTime, nullable=False)
    update_by_id = db.Column(db.String(20), nullable=False)
    update_dtime = db.Column(db.DateTime, nullable=False)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    __table_args__ = (
        db.ForeignKeyConstraint(['xfreturn_id', 'inventory_id'], ['rtintake.xfreturn_id', 'rtintake.inventory_id']),
    )
    
    item = db.relationship('Item', backref='return_intake_items')
    unit_of_measure = db.relationship('UnitOfMeasure')

class AgencyAccountRequest(db.Model):
    """Agency account creation request with workflow (S=submitted, R=review, A=approved, D=denied)"""
    __tablename__ = 'agency_account_request'
    
    request_id = db.Column(db.Integer, primary_key=True)
    
    agency_name = db.Column(db.String(120), nullable=False)
    contact_name = db.Column(db.String(80), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=False)
    contact_email = db.Column(db.String(200), nullable=False)
    reason_text = db.Column(db.String(255), nullable=False)
    
    agency_id = db.Column(db.Integer, db.ForeignKey('agency.agency_id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'))
    
    status_code = db.Column(db.CHAR(1), nullable=False)
    status_reason = db.Column(db.String(255))
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    agency = db.relationship('Agency', foreign_keys=[agency_id], backref='account_requests')
    user = db.relationship('User', foreign_keys=[user_id], backref='account_requests')
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='requests_created')
    updated_by = db.relationship('User', foreign_keys=[updated_by_id], backref='requests_updated')

class AgencyAccountRequestAudit(db.Model):
    """Immutable audit log for agency account request workflow events"""
    __tablename__ = 'agency_account_request_audit'
    
    audit_id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('agency_account_request.request_id'), nullable=False)
    event_type = db.Column(db.String(24), nullable=False)
    event_notes = db.Column(db.String(255))
    actor_user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    event_dtime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    version_nbr = db.Column(db.Integer, nullable=False, default=1)
    
    request = db.relationship('AgencyAccountRequest', backref='audit_log')
    actor = db.relationship('User', foreign_keys=[actor_user_id], backref='audit_actions')

class Notification(db.Model):
    """In-app notifications for users"""
    __tablename__ = 'notification'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.warehouse_id'))
    reliefrqst_id = db.Column(db.Integer, db.ForeignKey('reliefrqst.reliefrqst_id'))
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='unread')
    link_url = db.Column(db.String(500))
    payload = db.Column(db.Text)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')
    warehouse = db.relationship('Warehouse', backref='notifications')
    relief_request = db.relationship('ReliefRqst', backref='notifications')
