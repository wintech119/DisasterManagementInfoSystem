"""
Dashboard Blueprint - Role-Based Dashboards with Modern UI

Provides role-specific dashboard views matching the Relief Package preparation
UI/UX standards with summary cards, filter tabs, and modern styling.
"""

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func, desc
from app.db.models import (
    db, Inventory, Item, Warehouse, 
    Event, Donor, Agency, User, ReliefRqst, ReliefRequestFulfillmentLock
)
from app.services import relief_request_service as rr_service
from app.services.dashboard_service import DashboardService
from app.core.feature_registry import FeatureRegistry
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    """
    Main dashboard with role-based routing.
    Routes users to role-specific dashboards with modern UI.
    """
    primary_role = FeatureRegistry.get_primary_role(current_user)
    
    # Route to role-specific dashboards
    if primary_role == 'SYSTEM_ADMINISTRATOR':
        return admin_dashboard()
    elif primary_role in ['ODPEM_DG', 'ODPEM_DDG', 'ODPEM_DIR_PEOD']:
        return director_dashboard()
    elif primary_role in ['LOGISTICS_MANAGER', 'LOGISTICS_OFFICER']:
        return logistics_dashboard()
    elif primary_role in ['AGENCY_DISTRIBUTOR', 'AGENCY_SHELTER']:
        return agency_dashboard()
    elif primary_role == 'INVENTORY_CLERK':
        return inventory_dashboard()
    else:
        # Default dashboard for unrecognized roles
        return general_dashboard()


@dashboard_bp.route('/logistics')
@login_required
def logistics_dashboard():
    """
    Logistics dashboard with modern UI matching Relief Package preparation.
    For Logistics Officers and Logistics Managers.
    """
    # Get dashboard data from service
    dashboard_data = DashboardService.get_dashboard_data(current_user)
    
    # Get filter parameter
    current_filter = request.args.get('filter', 'pending')
    
    # Query fulfillment requests
    from sqlalchemy.orm import joinedload
    
    base_query = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.fulfillment_lock).joinedload(ReliefRequestFulfillmentLock.fulfiller)
    )
    
    # Apply filters
    if current_filter == 'pending':
        requests = base_query.filter(
            ReliefRqst.status_code == rr_service.STATUS_SUBMITTED,
            ~ReliefRqst.fulfillment_lock.has()
        ).order_by(desc(ReliefRqst.request_date)).all()
    elif current_filter == 'in_progress':
        requests = base_query.filter(
            ReliefRqst.fulfillment_lock.has()
        ).order_by(desc(ReliefRqst.request_date)).all()
    elif current_filter == 'ready':
        requests = base_query.filter_by(
            status_code=rr_service.STATUS_PART_FILLED
        ).order_by(desc(ReliefRqst.request_date)).all()
    elif current_filter == 'completed':
        requests = base_query.filter_by(
            status_code=rr_service.STATUS_FILLED
        ).order_by(desc(ReliefRqst.filled_date)).all()
    else:  # 'all'
        requests = base_query.filter(
            ReliefRqst.status_code.in_([
                rr_service.STATUS_SUBMITTED,
                rr_service.STATUS_PART_FILLED,
                rr_service.STATUS_FILLED
            ])
        ).order_by(desc(ReliefRqst.request_date)).all()
    
    # Calculate counts for filter tabs
    global_counts = {
        'pending': ReliefRqst.query.filter(
            ReliefRqst.status_code == rr_service.STATUS_SUBMITTED,
            ~ReliefRqst.fulfillment_lock.has()
        ).count(),
        'in_progress': ReliefRqst.query.filter(
            ReliefRqst.fulfillment_lock.has()
        ).count(),
        'ready': ReliefRqst.query.filter_by(status_code=rr_service.STATUS_PART_FILLED).count(),
        'completed': ReliefRqst.query.filter_by(status_code=rr_service.STATUS_FILLED).count(),
    }
    global_counts['all'] = sum(global_counts.values())
    
    # Inventory metrics
    low_stock_count = db.session.query(Item).join(Inventory).filter(
        Item.status_code == 'A'
    ).group_by(Item.item_id).having(
        func.sum(Inventory.usable_qty) <= Item.reorder_qty
    ).count()
    
    # Total inventory count (value calculation not available - no cost field in schema)
    total_inventory_value = 0
    
    context = {
        **dashboard_data,
        'requests': requests,
        'current_filter': current_filter,
        'global_counts': global_counts,
        'counts': global_counts,  # For compatibility
        'low_stock_count': low_stock_count,
        'total_inventory_value': total_inventory_value,
        'STATUS_SUBMITTED': rr_service.STATUS_SUBMITTED,
        'STATUS_PART_FILLED': rr_service.STATUS_PART_FILLED,
        'STATUS_FILLED': rr_service.STATUS_FILLED,
    }
    
    return render_template('dashboard/logistics.html', **context)


@dashboard_bp.route('/agency')
@login_required
def agency_dashboard():
    """
    Agency dashboard for relief agencies.
    Shows agency's relief requests with modern UI.
    """
    # Get dashboard data from service
    dashboard_data = DashboardService.get_dashboard_data(current_user)
    
    # Get filter parameter
    current_filter = request.args.get('filter', 'active')
    
    # Query agency's requests
    from sqlalchemy.orm import joinedload
    
    base_query = ReliefRqst.query.options(
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.eligible_event)
    ).filter_by(agency_id=current_user.agency_id)
    
    # Apply filters
    if current_filter == 'draft':
        requests = base_query.filter_by(status_code=0).order_by(desc(ReliefRqst.create_dtime)).all()
    elif current_filter == 'pending':
        requests = base_query.filter_by(status_code=1).order_by(desc(ReliefRqst.request_date)).all()
    elif current_filter == 'approved':
        requests = base_query.filter(
            ReliefRqst.status_code.in_([3, 5])
        ).order_by(desc(ReliefRqst.approval_date)).all()
    elif current_filter == 'completed':
        requests = base_query.filter_by(status_code=7).order_by(desc(ReliefRqst.filled_date)).all()
    else:  # 'active' - default
        requests = base_query.filter(
            ReliefRqst.status_code.in_([0, 1, 3, 5])
        ).order_by(desc(ReliefRqst.create_dtime)).all()
    
    # Calculate counts
    global_counts = {
        'draft': base_query.filter_by(status_code=0).count(),
        'pending': base_query.filter_by(status_code=1).count(),
        'approved': base_query.filter(ReliefRqst.status_code.in_([3, 5])).count(),
        'completed': base_query.filter_by(status_code=7).count(),
    }
    global_counts['active'] = global_counts['draft'] + global_counts['pending'] + global_counts['approved']
    
    context = {
        **dashboard_data,
        'requests': requests,
        'current_filter': current_filter,
        'global_counts': global_counts,
        'counts': global_counts,
    }
    
    return render_template('dashboard/agency.html', **context)


@dashboard_bp.route('/director')
@login_required
def director_dashboard():
    """
    Director dashboard for ODPEM executives.
    Shows eligibility review queue with modern UI.
    """
    # Get dashboard data from service
    dashboard_data = DashboardService.get_dashboard_data(current_user)
    
    # Get filter parameter
    current_filter = request.args.get('filter', 'pending')
    
    # Query requests
    from sqlalchemy.orm import joinedload
    
    base_query = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.event)
    )
    
    # Apply filters
    if current_filter == 'pending':
        requests = base_query.filter_by(status_code=1).order_by(desc(ReliefRqst.request_date)).all()
    elif current_filter == 'approved':
        requests = base_query.filter_by(status_code=3).order_by(desc(ReliefRqst.approval_date)).all()
    elif current_filter == 'in_progress':
        requests = base_query.filter(
            ReliefRqst.status_code.in_([1, 3, 5])
        ).order_by(desc(ReliefRqst.request_date)).all()
    elif current_filter == 'completed':
        requests = base_query.filter_by(status_code=7).order_by(desc(ReliefRqst.filled_date)).all()
    else:  # 'all'
        requests = base_query.order_by(desc(ReliefRqst.request_date)).all()
    
    # Calculate counts
    global_counts = {
        'pending': base_query.filter_by(status_code=1).count(),
        'approved': base_query.filter_by(status_code=3).count(),
        'in_progress': base_query.filter(ReliefRqst.status_code.in_([1, 3, 5])).count(),
        'completed': base_query.filter_by(status_code=7).count(),
    }
    global_counts['all'] = base_query.count()
    
    context = {
        **dashboard_data,
        'requests': requests,
        'current_filter': current_filter,
        'global_counts': global_counts,
        'counts': global_counts,
    }
    
    return render_template('dashboard/director.html', **context)


@dashboard_bp.route('/admin')
@login_required
def admin_dashboard():
    """
    System administrator dashboard with system-wide metrics.
    """
    dashboard_data = DashboardService.get_dashboard_data(current_user)
    
    # System metrics
    total_users = User.query.count()
    total_agencies = Agency.query.filter_by(status_code='A').count()
    total_warehouses = Warehouse.query.filter_by(status_code='A').count()
    total_items = Item.query.filter_by(status_code='A').count()
    total_events = Event.query.filter_by(status_code='A').count()
    
    # Recent activity
    recent_requests = ReliefRqst.query.order_by(desc(ReliefRqst.create_dtime)).limit(10).all()
    recent_users = User.query.order_by(desc(User.create_dtime)).limit(5).all()
    
    context = {
        **dashboard_data,
        'total_users': total_users,
        'total_agencies': total_agencies,
        'total_warehouses': total_warehouses,
        'total_items': total_items,
        'total_events': total_events,
        'recent_requests': recent_requests,
        'recent_users': recent_users,
    }
    
    return render_template('dashboard/admin.html', **context)


@dashboard_bp.route('/inventory')
@login_required
def inventory_dashboard():
    """
    Inventory clerk dashboard focused on stock management.
    """
    dashboard_data = DashboardService.get_dashboard_data(current_user)
    
    # Inventory metrics
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
    
    total_inventory_value = db.session.query(
        func.sum(Inventory.usable_qty * Item.unit_cost)
    ).join(Item).filter(
        Inventory.usable_qty > 0,
        Item.status_code == 'A'
    ).scalar() or 0
    
    context = {
        **dashboard_data,
        'low_stock_items': low_stock_items,
        'total_inventory_value': total_inventory_value,
    }
    
    return render_template('dashboard/inventory.html', **context)


@dashboard_bp.route('/general')
@login_required
def general_dashboard():
    """
    General dashboard for users without specific role dashboards.
    """
    dashboard_data = DashboardService.get_dashboard_data(current_user)
    
    context = {
        **dashboard_data,
    }
    
    return render_template('dashboard/general.html', **context)
