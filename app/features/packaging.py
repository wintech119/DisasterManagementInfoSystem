"""
Relief Request Packaging Blueprint
Allows Logistics Officers/Managers to prepare relief packages from approved requests
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from app.db import db
from app.db.models import (
    ReliefRqst, ReliefRqstItem, Item, Warehouse, Inventory,
    User, Notification, ReliefRequestFulfillmentLock
)
from app.core.rbac import has_permission, permission_required
from app.services import relief_request_service as rr_service
from app.services import fulfillment_lock_service as lock_service
from app.core.audit import add_audit_fields
from app.core.exceptions import OptimisticLockError


packaging_bp = Blueprint('packaging', __name__, url_prefix='/packaging')


@packaging_bp.route('/pending-fulfillment')
@login_required
def pending_fulfillment():
    """
    List all approved relief requests awaiting package preparation.
    Shows SUBMITTED (3) and PART_FILLED (5) requests for LO/LM to fulfill.
    """
    from app.core.rbac import is_logistics_officer, is_logistics_manager
    if not (is_logistics_officer() or is_logistics_manager()):
        flash('Access denied. Only Logistics Officers and Managers can view this page.', 'danger')
        abort(403)
    
    filter_type = request.args.get('filter', 'awaiting')
    
    base_query = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.fulfillment_lock).joinedload(ReliefRequestFulfillmentLock.fulfiller)
    ).filter(
        ReliefRqst.status_code.in_([rr_service.STATUS_SUBMITTED, rr_service.STATUS_PART_FILLED])
    )
    
    all_requests = base_query.all()
    
    if filter_type == 'awaiting':
        filtered_requests = [r for r in all_requests if r.status_code == rr_service.STATUS_SUBMITTED and not r.fulfillment_lock]
    elif filter_type == 'in_progress':
        filtered_requests = [r for r in all_requests if r.fulfillment_lock]
    elif filter_type == 'ready':
        filtered_requests = [r for r in all_requests if r.status_code == rr_service.STATUS_PART_FILLED]
    else:
        filtered_requests = all_requests
    
    global_counts = {
        'submitted': len([r for r in all_requests if r.status_code == rr_service.STATUS_SUBMITTED and not r.fulfillment_lock]),
        'locked': len([r for r in all_requests if r.fulfillment_lock]),
        'part_filled': len([r for r in all_requests if r.status_code == rr_service.STATUS_PART_FILLED])
    }
    
    filtered_counts = {
        'submitted': len([r for r in filtered_requests if r.status_code == rr_service.STATUS_SUBMITTED and not r.fulfillment_lock]),
        'locked': len([r for r in filtered_requests if r.fulfillment_lock]),
        'part_filled': len([r for r in filtered_requests if r.status_code == rr_service.STATUS_PART_FILLED and not r.fulfillment_lock])
    }
    
    return render_template('packaging/pending_fulfillment.html',
                         requests=filtered_requests,
                         counts=filtered_counts,
                         global_counts=global_counts,
                         current_filter=filter_type,
                         STATUS_SUBMITTED=rr_service.STATUS_SUBMITTED,
                         STATUS_PART_FILLED=rr_service.STATUS_PART_FILLED)


@packaging_bp.route('/<int:reliefrqst_id>/prepare', methods=['GET', 'POST'])
@login_required
def prepare_package(reliefrqst_id):
    """
    Main packaging page - shows all items and warehouse allocations.
    Handles both GET (display) and POST (save/submit).
    """
    from app.core.rbac import is_logistics_officer, is_logistics_manager
    if not (is_logistics_officer() or is_logistics_manager()):
        flash('Access denied. Only Logistics Officers and Managers can prepare packages.', 'danger')
        abort(403)
    relief_request = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.category),
        joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.default_uom),
        joinedload(ReliefRqst.fulfillment_lock).joinedload(ReliefRequestFulfillmentLock.fulfiller)
    ).get_or_404(reliefrqst_id)
    
    if relief_request.status_code not in [rr_service.STATUS_SUBMITTED, rr_service.STATUS_PART_FILLED]:
        flash(f'Only SUBMITTED or PART FILLED requests can be packaged. Current status: {relief_request.status.status_desc}', 'danger')
        return redirect(url_for('packaging.pending_fulfillment'))
    
    can_edit, blocking_user, lock = lock_service.check_lock(reliefrqst_id, current_user.user_id)
    
    if request.method == 'GET':
        if not lock:
            success, message, lock = lock_service.acquire_lock(
                reliefrqst_id, 
                current_user.user_id, 
                current_user.email
            )
            if not success:
                can_edit = False
                blocking_user = message.replace("Currently being prepared by ", "")
        
        warehouses = Warehouse.query.filter_by(status_code='A').order_by(Warehouse.warehouse_name).all()
        
        item_inventory_map = {}
        for item in relief_request.items:
            inventories = Inventory.query.filter_by(
                item_id=item.item_id,
                status_code='A'
            ).filter(
                Inventory.usable_qty > 0
            ).join(Warehouse).order_by(Warehouse.warehouse_name).all()
            
            item_inventory_map[item.item_id] = inventories
        
        from app.core.rbac import is_logistics_officer, is_logistics_manager
        
        return render_template('packaging/prepare.html',
                             relief_request=relief_request,
                             warehouses=warehouses,
                             item_inventory_map=item_inventory_map,
                             can_edit=can_edit,
                             blocking_user=blocking_user,
                             lock=lock,
                             is_locked_by_me=(lock and lock.fulfiller_user_id == current_user.user_id),
                             is_logistics_officer=is_logistics_officer(),
                             is_logistics_manager=is_logistics_manager())
    
    if not can_edit:
        flash(f'This request is currently being prepared by {blocking_user}', 'warning')
        return redirect(url_for('packaging.pending_fulfillment'))
    
    action = request.form.get('action')
    
    if action == 'save_draft':
        return _save_draft(relief_request)
    elif action == 'submit_for_approval':
        return _submit_for_approval(relief_request)
    elif action == 'send_for_dispatch':
        return _send_for_dispatch(relief_request)
    else:
        flash('Invalid action', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=reliefrqst_id))


def _save_draft(relief_request):
    """Save packaging progress as draft (lock retained for continued editing)"""
    try:
        _process_allocations(relief_request, validate_complete=False)
        
        db.session.commit()
        flash(f'Draft saved for relief request #{relief_request.reliefrqst_id}', 'success')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))


def _submit_for_approval(relief_request):
    """Submit package for Logistics Manager approval (LO only)"""
    from app.core.rbac import is_logistics_officer
    if not is_logistics_officer():
        flash('Only Logistics Officers can submit for approval', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
    
    try:
        _process_allocations(relief_request, validate_complete=True)
        
        relief_request.action_by_id = current_user.email[:20]
        relief_request.action_dtime = datetime.now()
        relief_request.version_nbr += 1
        
        db.session.commit()
        
        lock_service.release_lock(relief_request.reliefrqst_id, current_user.user_id)
        
        flash(f'Relief request #{relief_request.reliefrqst_id} submitted for Logistics Manager approval', 'success')
        return redirect(url_for('packaging.pending_fulfillment'))
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))


def _send_for_dispatch(relief_request):
    """Send package for dispatch (LM only)"""
    from app.core.rbac import is_logistics_manager
    if not is_logistics_manager():
        flash('Only Logistics Managers can send for dispatch', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
    
    try:
        _process_allocations(relief_request, validate_complete=True)
        
        relief_request.action_by_id = current_user.email[:20]
        relief_request.action_dtime = datetime.now()
        relief_request.status_code = rr_service.STATUS_PART_FILLED
        relief_request.version_nbr += 1
        
        db.session.commit()
        
        lock_service.release_lock(relief_request.reliefrqst_id, current_user.user_id, force=True)
        
        flash(f'Relief request #{relief_request.reliefrqst_id} sent for dispatch', 'success')
        return redirect(url_for('packaging.pending_fulfillment'))
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))


def _process_allocations(relief_request, validate_complete=False):
    """
    Process warehouse allocations from form data.
    Updates issue_qty and item status codes.
    
    Args:
        relief_request: The ReliefRqst being packaged
        validate_complete: If True, ensures all items are fully allocated
    """
    for item in relief_request.items:
        item_id = item.item_id
        request_qty = item.request_qty
        
        total_allocated = Decimal('0')
        warehouse_allocations = []
        
        allocation_keys = [k for k in request.form.keys() if k.startswith(f'allocation_{item_id}_')]
        
        for key in allocation_keys:
            parts = key.split('_')
            if len(parts) >= 3:
                warehouse_id = int(parts[2])
                allocated_qty = Decimal(request.form.get(key) or '0')
                
                if allocated_qty > 0:
                    inventory = Inventory.query.filter_by(
                        warehouse_id=warehouse_id,
                        item_id=item_id,
                        status_code='A'
                    ).first()
                    
                    if not inventory:
                        raise ValueError(f'No active inventory found for item {item_id} at warehouse {warehouse_id}')
                    
                    if allocated_qty > inventory.usable_qty:
                        raise ValueError(f'Allocated quantity ({allocated_qty}) exceeds usable quantity ({inventory.usable_qty}) for item {item.item.item_name} at warehouse {inventory.warehouse.warehouse_name}')
                    
                    total_allocated += allocated_qty
                    warehouse_allocations.append((inventory, allocated_qty))
        
        if total_allocated > request_qty:
            raise ValueError(f'Total allocated quantity ({total_allocated}) exceeds requested quantity ({request_qty}) for item {item.item.item_name}')
        
        if validate_complete and total_allocated < request_qty:
            raise ValueError(f'Item {item.item.item_name} is not fully allocated ({total_allocated} of {request_qty})')
        
        item.issue_qty = total_allocated
        
        if total_allocated == Decimal('0'):
            status_code = request.form.get(f'status_{item_id}', 'U')
            if status_code not in ['D', 'U', 'W']:
                raise ValueError(f'Items with zero allocation must have status D, U, or W')
            item.status_code = status_code
        elif total_allocated >= request_qty:
            item.status_code = 'F'
        else:
            manual_status = request.form.get(f'status_{item_id}')
            if manual_status == 'L':
                item.status_code = 'L'
            else:
                item.status_code = 'P'
        
        item.action_by_id = current_user.email[:20]
        item.action_dtime = datetime.now()
        item.version_nbr += 1


@packaging_bp.route('/api/inventory/<int:item_id>/<int:warehouse_id>')
@login_required
def get_inventory(item_id, warehouse_id):
    """API endpoint to get current inventory for an item at a warehouse"""
    inventory = Inventory.query.filter_by(
        item_id=item_id,
        warehouse_id=warehouse_id,
        status_code='A'
    ).first()
    
    if inventory:
        return jsonify({
            'usable_qty': float(inventory.usable_qty or 0),
            'reserved_qty': float(inventory.reserved_qty or 0),
            'defective_qty': float(inventory.defective_qty or 0)
        })
    else:
        return jsonify({
            'usable_qty': 0,
            'reserved_qty': 0,
            'defective_qty': 0
        })
