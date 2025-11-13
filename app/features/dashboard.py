from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, desc
from app.db.models import (
    db, Inventory, Item, Warehouse, 
    Event, Donor, Agency, User, ReliefRqst, ReliefRequestFulfillmentLock
)
from app.services import relief_request_service as rr_service
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    from flask_login import current_user
    from app.db.models import ItemCateg
    
    user_role_codes = [r.code for r in current_user.roles] if current_user.roles else []
    user_role_names = [r.name for r in current_user.roles] if current_user.roles else []
    
    total_items = Item.query.filter_by(status_code='A').count()
    total_warehouses = Warehouse.query.filter_by(status_code='A').count()
    total_events = Event.query.filter_by(status_code='A').count()
    total_users = User.query.count()
    
    total_inventory_value = db.session.query(
        func.sum(Inventory.usable_qty * Item.unit_cost)
    ).join(Item).filter(
        Inventory.usable_qty > 0,
        Item.status_code == 'A'
    ).scalar() or 0
    
    low_stock_items = db.session.query(
        Item.item_id, 
        Item.item_name,
        func.sum(Inventory.usable_qty).label('total_qty'),
        Item.reorder_level
    ).join(Inventory).filter(
        Item.status_code == 'A'
    ).group_by(
        Item.item_id, Item.item_name, Item.reorder_level
    ).having(
        func.sum(Inventory.usable_qty) <= Item.reorder_level
    ).limit(10).all()
    
    warehouse_stock = db.session.query(
        Warehouse.warehouse_id,
        Warehouse.warehouse_name,
        func.count(Inventory.item_id).label('item_count'),
        func.sum(Inventory.usable_qty).label('total_qty')
    ).join(Inventory).filter(
        Warehouse.status_code == 'A',
        Inventory.usable_qty > 0
    ).group_by(
        Warehouse.warehouse_id, Warehouse.warehouse_name
    ).all()
    
    active_events = Event.query.filter_by(status_code='A').order_by(desc(Event.event_start_date)).limit(5).all()
    
    category_distribution = db.session.query(
        ItemCateg.catg_desc,
        func.count(Item.item_id).label('item_count'),
        func.sum(Inventory.usable_qty).label('total_qty')
    ).join(Item).join(Inventory).filter(
        Item.status_code == 'A',
        Inventory.usable_qty > 0
    ).group_by(ItemCateg.catg_desc).all()
    
    from sqlalchemy.orm import joinedload
    from app.db.models import ReliefRqstStatus
    
    pending_fulfillment_requests = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.fulfillment_lock).joinedload(ReliefRequestFulfillmentLock.fulfiller)
    ).filter(
        ReliefRqst.status_code.in_([rr_service.STATUS_SUBMITTED, rr_service.STATUS_PART_FILLED])
    ).all()
    
    packaging_counts = {
        'awaiting': len([r for r in pending_fulfillment_requests if r.status_code == rr_service.STATUS_SUBMITTED and not r.fulfillment_lock]),
        'in_progress': len([r for r in pending_fulfillment_requests if r.fulfillment_lock]),
        'ready': len([r for r in pending_fulfillment_requests if r.status_code == rr_service.STATUS_PART_FILLED])
    }
    
    context = {
        'now': datetime.now(),
        'total_items': total_items,
        'total_warehouses': total_warehouses,
        'total_events': total_events,
        'total_users': total_users,
        'total_inventory_value': total_inventory_value,
        'low_stock_items': low_stock_items,
        'warehouse_stock': warehouse_stock,
        'active_events': active_events,
        'category_distribution': category_distribution,
        'packaging_counts': packaging_counts,
        'pending_fulfillment_requests': pending_fulfillment_requests[:5],
        'STATUS_SUBMITTED': rr_service.STATUS_SUBMITTED,
        'STATUS_PART_FILLED': rr_service.STATUS_PART_FILLED
    }
    
    if 'Logistics Manager' in user_role_names or 'LOG_MGR' in user_role_codes:
        return render_template('dashboard/logistics_manager.html', **context)
    elif 'Logistics Officer' in user_role_names or 'LOG_OFFICER' in user_role_codes:
        return render_template('dashboard/logistics_officer.html', **context)
    elif 'Logistics Executive' in user_role_names or 'LOG_EXEC' in user_role_codes:
        return render_template('dashboard/logistics_executive.html', **context)
    else:
        return render_template('dashboard/index.html', **context)
