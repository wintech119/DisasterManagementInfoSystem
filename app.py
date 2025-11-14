"""
DRIMS - Disaster Relief Inventory Management System
Main Flask Application
"""
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import os

from app.db import db, init_db
from app.db.models import User, Role, Event, Warehouse, Item, Inventory, Agency, ReliefRqst
from settings import Config

app = Flask(__name__)
app.config.from_object(Config)

init_db(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

from app.features.events import events_bp
from app.features.warehouses import warehouses_bp
from app.features.items import items_bp
from app.features.inventory import inventory_bp
from app.features.requests_aidmgmt import requests_bp
from app.features.packaging import packaging_bp
from app.features.donations import donations_bp
from app.features.intake_aidmgmt import bp as intake_bp
from app.features.user_admin import user_admin_bp
from app.features.donors import donors_bp
from app.features.agencies import agencies_bp
from app.features.custodians import custodians_bp
from app.features.dashboard import dashboard_bp
from app.features.transfers import transfers_bp
from app.features.locations import locations_bp
from app.features.notifications import notifications_bp
from app.features.reports import reports_bp
from app.features.account_requests import account_requests_bp
from app.features.eligibility import eligibility_bp
from app.features.odpem_director import director_bp
from app.core.status import get_status_label, get_status_badge_class
from app.core.rbac import (
    has_role, has_all_roles, has_warehouse_access,
    is_admin, is_logistics_manager, is_logistics_officer, is_director_level,
    can_manage_users, can_view_reports, has_permission
)

app.jinja_env.globals.update(
    has_role=has_role,
    has_all_roles=has_all_roles,
    has_warehouse_access=has_warehouse_access,
    is_admin=is_admin,
    is_logistics_manager=is_logistics_manager,
    is_logistics_officer=is_logistics_officer,
    is_director_level=is_director_level,
    can_manage_users=can_manage_users,
    can_view_reports=can_view_reports,
    has_permission=has_permission
)

@app.template_filter('format_date')
def format_date_filter(date_val, format_str='%Y-%m-%d'):
    """Format date to YYYY-MM-DD (or custom format)"""
    if date_val is None:
        return ''
    if isinstance(date_val, str):
        return date_val
    return date_val.strftime(format_str)

app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
app.register_blueprint(events_bp)
app.register_blueprint(warehouses_bp)
app.register_blueprint(items_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(requests_bp)
app.register_blueprint(packaging_bp)
app.register_blueprint(donations_bp)
app.register_blueprint(intake_bp)
app.register_blueprint(user_admin_bp, url_prefix='/users')
app.register_blueprint(donors_bp, url_prefix='/donors')
app.register_blueprint(agencies_bp, url_prefix='/agencies')
app.register_blueprint(custodians_bp, url_prefix='/custodians')
app.register_blueprint(transfers_bp, url_prefix='/transfers')
app.register_blueprint(locations_bp, url_prefix='/locations')
app.register_blueprint(notifications_bp, url_prefix='/notifications')
app.register_blueprint(reports_bp, url_prefix='/reports')
app.register_blueprint(account_requests_bp)
app.register_blueprint(eligibility_bp)
app.register_blueprint(director_bp)

@app.template_filter('status_badge')
def status_badge_filter(status_code, entity_type):
    """Return Bootstrap badge color class for status codes"""
    return get_status_badge_class(status_code, entity_type)

@app.template_filter('status_label')
def status_label_filter(status_code, entity_type):
    """Return human-readable label for status codes"""
    return get_status_label(status_code, entity_type)

@app.context_processor
def inject_now():
    """Inject current datetime for footer year and other templates"""
    from datetime import datetime
    return {'now': datetime.utcnow()}

@app.route('/')
@login_required
def index():
    """Home dashboard with KPI cards"""
    from sqlalchemy import func
    
    total_warehouses = Warehouse.query.filter_by(status_code='A').count()
    total_items = Item.query.filter_by(status_code='A').count()
    active_events = Event.query.filter_by(status_code='A').count()
    pending_requests = ReliefRqst.query.filter(ReliefRqst.status_code.in_([0, 1, 3])).count()
    
    total_stock_value = db.session.query(
        func.sum(Inventory.usable_qty)
    ).filter_by(status_code='A').scalar() or 0
    
    low_stock_items = db.session.query(func.count(Inventory.inventory_id)).filter(
        Inventory.usable_qty < Item.reorder_qty,
        Inventory.item_id == Item.item_id,
        Inventory.status_code == 'A'
    ).scalar() or 0
    
    return render_template('index.html',
                         total_warehouses=total_warehouses,
                         total_items=total_items,
                         active_events=active_events,
                         pending_requests=pending_requests,
                         total_stock_value=total_stock_value,
                         low_stock_items=low_stock_items)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('index'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
