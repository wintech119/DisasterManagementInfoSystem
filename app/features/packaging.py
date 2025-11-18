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
    ReliefRqst, ReliefRqstItem, Item, Warehouse, Inventory, ItemBatch,
    User, Notification, ReliefRequestFulfillmentLock,
    ReliefPkg, ReliefPkgItem, ReliefRqstItemStatus
)
from app.core.rbac import has_permission, permission_required
from app.services import relief_request_service as rr_service
from app.services import fulfillment_lock_service as lock_service
from app.services import item_status_service
from app.services import inventory_reservation_service as reservation_service
from app.services.batch_allocation_service import BatchAllocationService
from app.core.audit import add_audit_fields
from app.core.exceptions import OptimisticLockError


packaging_bp = Blueprint('packaging', __name__, url_prefix='/packaging')


@packaging_bp.route('/pending-approval')
@login_required
def pending_approval():
    """
    LM approval queue - shows packages submitted by LO awaiting LM approval.
    
    Criteria for "Pending LM Approval":
    - Relief Request status = SUBMITTED (approved by director, ready for fulfillment)
    - ReliefPkg exists with status_code='P' (Pending - submitted for approval)
    - No active fulfillment lock (LO released lock after submission)
    - Not yet dispatched (dispatch_dtime is NULL)
    """
    from app.core.rbac import is_logistics_manager
    if not is_logistics_manager():
        flash('Access denied. Only Logistics Managers can view this page.', 'danger')
        abort(403)
    
    # Find all relief requests with packages awaiting LM approval
    # Note: fulfillment_lock backref uses uselist=False, so it's either an object or None
    all_requests = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.packages),
        joinedload(ReliefRqst.fulfillment_lock).joinedload(ReliefRequestFulfillmentLock.fulfiller)
    ).filter(
        ReliefRqst.status_code == rr_service.STATUS_SUBMITTED
    ).order_by(ReliefRqst.create_dtime.desc()).all()
    
    # Filter to requests with packages pending LM approval
    pending_requests = []
    for req in all_requests:
        # Check if there's a ReliefPkg for this request with status='P' (submitted for approval)
        relief_pkg = next((pkg for pkg in req.packages if pkg.status_code == rr_service.PKG_STATUS_PENDING), None)
        
        if relief_pkg and not req.fulfillment_lock and relief_pkg.dispatch_dtime is None:
            # Package exists, is pending approval, no active lock, and not yet dispatched
            pending_requests.append(req)
    
    counts = {
        'pending_approval': len(pending_requests)
    }
    
    return render_template('packaging/pending_approval.html',
                         requests=pending_requests,
                         counts=counts,
                         STATUS_SUBMITTED=rr_service.STATUS_SUBMITTED,
                         PKG_STATUS_PENDING=rr_service.PKG_STATUS_PENDING)


@packaging_bp.route('/<int:reliefrqst_id>/review-approval', methods=['GET', 'POST'])
@login_required
def review_approval(reliefrqst_id):
    """
    LM reviews LO-submitted package and approves for dispatch.
    GET: Display allocations for review
    POST: Approve and dispatch to inventory clerk
    """
    from app.core.rbac import is_logistics_manager
    if not is_logistics_manager():
        flash('Access denied. Only Logistics Managers can review and approve packages.', 'danger')
        abort(403)
    
    relief_request = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.category),
        joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.default_uom),
        joinedload(ReliefRqst.packages)
    ).get_or_404(reliefrqst_id)
    
    # Get the pending ReliefPkg
    relief_pkg = next((pkg for pkg in relief_request.packages if pkg.status_code == rr_service.PKG_STATUS_PENDING), None)
    
    if not relief_pkg:
        flash('No pending package found for this relief request.', 'danger')
        return redirect(url_for('packaging.pending_approval'))
    
    if relief_pkg.dispatch_dtime is not None:
        flash('This package has already been dispatched.', 'warning')
        return redirect(url_for('packaging.pending_approval'))
    
    if request.method == 'GET':
        # Load allocations for display
        warehouses = Warehouse.query.filter_by(status_code='A').order_by(Warehouse.warehouse_name).all()
        
        # Build allocation map from ReliefPkgItem
        allocations = {}
        for pkg_item in relief_pkg.items:
            item_id = pkg_item.item_id
            warehouse_id = Inventory.query.get(pkg_item.fr_inventory_id).warehouse_id
            
            if item_id not in allocations:
                allocations[item_id] = {}
            
            allocations[item_id][warehouse_id] = pkg_item.item_qty
        
        return render_template('packaging/review_approval.html',
                             relief_request=relief_request,
                             relief_pkg=relief_pkg,
                             warehouses=warehouses,
                             allocations=allocations)
    
    # POST: Approve and dispatch
    action = request.form.get('action')
    
    if action == 'approve_and_dispatch':
        try:
            # Verify at least one item has allocated quantity (support partial fulfillment)
            has_allocated_items = any(item.issue_qty > 0 for item in relief_request.items)
            if not has_allocated_items:
                raise ValueError('Cannot dispatch package: no items have been allocated')
            
            # LM approval: set verify_by_id and verify_dtime
            relief_pkg.verify_by_id = current_user.user_name
            relief_pkg.verify_dtime = datetime.now()
            
            # Mark package as dispatched
            relief_pkg.status_code = rr_service.PKG_STATUS_DISPATCHED
            relief_pkg.dispatch_dtime = datetime.now()
            relief_pkg.update_by_id = current_user.user_name
            relief_pkg.update_dtime = datetime.now()
            
            # Commit inventory: convert reservations to actual deductions
            success, error_msg = reservation_service.commit_inventory(relief_request.reliefrqst_id)
            if not success:
                raise ValueError(f'Inventory commit failed: {error_msg}')
            
            # Update relief request status
            relief_request.action_by_id = current_user.user_name
            relief_request.action_dtime = datetime.now()
            relief_request.status_code = rr_service.STATUS_PART_FILLED
            relief_request.version_nbr += 1
            
            # Notify logistics officers and agency users about package approval
            try:
                from app.services.notification_service import NotificationService
                
                # Notify logistics officers
                lo_users = NotificationService.get_active_users_by_role_codes(['LOGISTICS_OFFICER'])
                
                # Notify agency users
                agency_users = []
                if relief_request.agency_id:
                    agency_users = NotificationService.get_agency_active_users(relief_request.agency_id)
                
                all_recipients = lo_users + agency_users
                approver_name = f"{current_user.first_name} {current_user.last_name}" if current_user.first_name else current_user.email.split('@')[0]
                
                NotificationService.create_package_approved_notification(
                    relief_pkg=relief_pkg,
                    recipient_users=all_recipients,
                    approver_name=approver_name
                )
            except Exception as e:
                # Don't fail dispatch if notification fails
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Failed to send approval notification: {str(e)}')
            
            db.session.commit()
            
            flash(f'Relief request #{relief_request.reliefrqst_id} approved and dispatched to inventory clerk', 'success')
            return redirect(url_for('packaging.pending_approval'))
            
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return redirect(url_for('packaging.review_approval', reliefrqst_id=reliefrqst_id))
    
    elif action == 'reject':
        # TODO: Implement rejection workflow (send back to LO for revision)
        flash('Rejection workflow not yet implemented', 'info')
        return redirect(url_for('packaging.review_approval', reliefrqst_id=reliefrqst_id))
    
    else:
        flash('Invalid action', 'danger')
        return redirect(url_for('packaging.review_approval', reliefrqst_id=reliefrqst_id))


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
    ).order_by(ReliefRqst.create_dtime.desc())
    
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
        
        existing_packages = ReliefPkg.query.filter_by(reliefrqst_id=reliefrqst_id).all()
        
        existing_allocations = {}
        for pkg in existing_packages:
            for pkg_item in pkg.items:
                item_id = pkg_item.item_id
                warehouse_id = Inventory.query.get(pkg_item.fr_inventory_id).warehouse_id
                
                if item_id not in existing_allocations:
                    existing_allocations[item_id] = {}
                
                if warehouse_id not in existing_allocations[item_id]:
                    existing_allocations[item_id][warehouse_id] = Decimal('0')
                
                existing_allocations[item_id][warehouse_id] += pkg_item.item_qty
        
        # Load active item statuses
        status_map = item_status_service.load_status_map()
        
        # Compute allowed status options for each item based on allocation state
        item_status_options = {}
        for item in relief_request.items:
            # Calculate total allocated for this item
            total_allocated = Decimal('0')
            if item.item_id in existing_allocations:
                for warehouse_qty in existing_allocations[item.item_id].values():
                    total_allocated += warehouse_qty
            
            # Get auto status and allowed transitions
            auto_status, allowed_codes = item_status_service.compute_allowed_statuses(
                item.status_code,
                total_allocated,
                item.request_qty
            )
            
            item_status_options[item.item_id] = {
                'auto_status': auto_status,
                'allowed_codes': allowed_codes,
                'total_allocated': float(total_allocated)
            }
        
        return render_template('packaging/prepare.html',
                             relief_request=relief_request,
                             warehouses=warehouses,
                             item_inventory_map=item_inventory_map,
                             existing_allocations=existing_allocations,
                             can_edit=can_edit,
                             blocking_user=blocking_user,
                             lock=lock,
                             is_locked_by_me=(lock and lock.fulfiller_user_id == current_user.user_id),
                             status_map=status_map,
                             item_status_options=item_status_options)
    
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
        # Process and validate allocations
        new_allocations = _process_allocations(relief_request, validate_complete=False)
        
        # Flush to persist allocations before calculating reservation deltas
        db.session.flush()
        
        # Update inventory reservations (pass old allocations for delta calculation)
        old_allocations = relief_request._old_allocations if hasattr(relief_request, '_old_allocations') else {}
        success, error_msg = reservation_service.reserve_inventory(
            relief_request.reliefrqst_id,
            new_allocations,
            old_allocations
        )
        if not success:
            raise ValueError(f'Reservation failed: {error_msg}')
        
        db.session.commit()
        flash(f'Draft saved for relief request #{relief_request.reliefrqst_id}', 'success')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))


def _submit_for_approval(relief_request):
    """
    Submit package for Logistics Manager approval (LO only) - allows partial allocations.
    Workflow: LO fulfills → Submit to LM → LM approves → Dispatch to Inventory Clerk
    
    Note: LO submission preserves any existing verify_* audit fields. The "pending LM approval"
    state is indicated by: status_code='P' + no active lock + verify_by_id is NULL (first submission)
    or verify_by_id has value (resubmission after previous LM approval).
    """
    from app.core.rbac import is_logistics_officer
    if not is_logistics_officer():
        flash('Only Logistics Officers can submit for approval', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
    
    try:
        # Process and validate allocations
        new_allocations = _process_allocations(relief_request, validate_complete=False)
        
        # Get the ReliefPkg that was created/updated by _process_allocations
        relief_pkg = ReliefPkg.query.filter_by(reliefrqst_id=relief_request.reliefrqst_id).first()
        if not relief_pkg:
            raise ValueError('Failed to create relief package')
        
        # Keep package as Pending - DO NOT modify verify_by_id (preserves audit trail)
        # "Pending LM approval" = status_code='P' + no lock + verify_by_id is NULL or non-NULL
        relief_pkg.status_code = rr_service.PKG_STATUS_PENDING
        relief_pkg.update_by_id = current_user.user_name
        relief_pkg.update_dtime = datetime.now()
        
        # Flush to persist allocations before calculating reservation deltas
        db.session.flush()
        
        # Update inventory reservations (pass old allocations for delta calculation)
        old_allocations = relief_request._old_allocations if hasattr(relief_request, '_old_allocations') else {}
        success, error_msg = reservation_service.reserve_inventory(
            relief_request.reliefrqst_id,
            new_allocations,
            old_allocations
        )
        if not success:
            raise ValueError(f'Reservation failed: {error_msg}')
        
        # Notify all Logistics Managers about the pending approval
        try:
            from app.services.notification_service import NotificationService
            lm_users = NotificationService.get_active_users_by_role_codes(['LOGISTICS_MANAGER'])
            preparer_name = f"{current_user.first_name} {current_user.last_name}" if current_user.first_name else current_user.email.split('@')[0]
            NotificationService.create_package_ready_for_approval_notification(
                relief_pkg=relief_pkg,
                recipient_users=lm_users,
                preparer_name=preparer_name
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Failed to send LM approval notification: {str(e)}')
        
        db.session.commit()
        
        lock_service.release_lock(relief_request.reliefrqst_id, current_user.user_id)
        
        flash(f'Relief request #{relief_request.reliefrqst_id} submitted for Logistics Manager approval', 'success')
        return redirect(url_for('packaging.pending_fulfillment'))
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))


def _send_for_dispatch(relief_request):
    """
    Send package for dispatch (LM only).
    Workflow: LM fulfills directly → Dispatch to Inventory Clerk (bypasses approval)
    """
    from app.core.rbac import is_logistics_manager
    if not is_logistics_manager():
        flash('Only Logistics Managers can send for dispatch', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
    
    try:
        # Process and validate allocations (must be complete)
        new_allocations = _process_allocations(relief_request, validate_complete=True)
        
        # Get the ReliefPkg that was created/updated by _process_allocations
        relief_pkg = ReliefPkg.query.filter_by(reliefrqst_id=relief_request.reliefrqst_id).first()
        if not relief_pkg:
            raise ValueError('Failed to create relief package')
        
        # LM approval: set verify_by_id to current LM (bypasses LO approval step)
        relief_pkg.verify_by_id = current_user.user_name
        relief_pkg.verify_dtime = datetime.now()
        
        # Mark package as dispatched
        relief_pkg.status_code = rr_service.PKG_STATUS_DISPATCHED
        relief_pkg.dispatch_dtime = datetime.now()
        relief_pkg.update_by_id = current_user.user_name
        relief_pkg.update_dtime = datetime.now()
        
        # Flush to persist allocations
        db.session.flush()
        
        # Commit inventory: convert reservations to actual deductions
        success, error_msg = reservation_service.commit_inventory(relief_request.reliefrqst_id)
        if not success:
            raise ValueError(f'Inventory commit failed: {error_msg}')
        
        # Update relief request status
        relief_request.action_by_id = current_user.user_name
        relief_request.action_dtime = datetime.now()
        relief_request.status_code = rr_service.STATUS_PART_FILLED
        relief_request.version_nbr += 1
        
        # Notify agency users and logistics managers about dispatch
        try:
            from app.services.notification_service import NotificationService
            
            # Notify agency users
            agency_users = []
            if relief_request.agency_id:
                agency_users = NotificationService.get_agency_active_users(relief_request.agency_id)
            
            # Optionally notify logistics managers
            lm_users = NotificationService.get_active_users_by_role_codes(['LOGISTICS_MANAGER'])
            
            all_recipients = agency_users + lm_users
            dispatcher_name = f"{current_user.first_name} {current_user.last_name}" if current_user.first_name else current_user.email.split('@')[0]
            
            NotificationService.create_package_dispatched_notification(
                relief_pkg=relief_pkg,
                recipient_users=all_recipients,
                dispatcher_name=dispatcher_name
            )
        except Exception as e:
            # Don't fail dispatch if notification fails
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Failed to send dispatch notification: {str(e)}')
        
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
    Process batch-level allocations from form data.
    Updates issue_qty and item status codes, and persists allocations to ReliefPkgItem.
    
    Args:
        relief_request: The ReliefRqst being packaged
        validate_complete: If True, ensures all items are fully allocated
    
    Returns:
        List of new allocations for inventory reservation
    """
    new_allocations = []
    
    # Get or create ReliefPkg for this relief request
    relief_pkg = ReliefPkg.query.filter_by(reliefrqst_id=relief_request.reliefrqst_id).first()
    if not relief_pkg:
        # Create a new relief package for tracking allocations
        relief_pkg = ReliefPkg(
            reliefrqst_id=relief_request.reliefrqst_id,
            to_inventory_id=1,  # Placeholder, will be updated on dispatch
            start_date=date.today(),
            status_code='P',  # Preparing
            create_by_id=current_user.user_name,
            create_dtime=datetime.now(),
            update_by_id=current_user.user_name,
            update_dtime=datetime.now(),
            verify_by_id=current_user.user_name,
            received_by_id=current_user.user_name,
            version_nbr=1
        )
        db.session.add(relief_pkg)
        db.session.flush()  # Get the reliefpkg_id
    
    # CRITICAL: Capture existing allocations BEFORE deletion for reservation delta calculation
    existing_pkg_items = ReliefPkgItem.query.filter_by(reliefpkg_id=relief_pkg.reliefpkg_id).all()
    existing_allocations_map = {}
    for pkg_item in existing_pkg_items:
        # Track by (item_id, batch_id) for batch-level reservations
        existing_allocations_map[(pkg_item.item_id, pkg_item.batch_id)] = pkg_item.item_qty
    
    # Store old allocations on relief_request object for access in save/submit functions
    relief_request._old_allocations = existing_allocations_map
    
    # Now clear existing package items to rebuild from form data
    ReliefPkgItem.query.filter_by(reliefpkg_id=relief_pkg.reliefpkg_id).delete()
    
    for item in relief_request.items:
        item_id = item.item_id
        request_qty = item.request_qty
        
        total_allocated = Decimal('0')
        batch_allocations = []
        
        # Look for batch allocation keys: batch_allocation_{item_id}_{batch_id}
        allocation_keys = [k for k in request.form.keys() if k.startswith(f'batch_allocation_{item_id}_')]
        
        # Sort keys to ensure deterministic locking order (prevent deadlocks)
        allocation_keys = sorted(allocation_keys)
        
        for key in allocation_keys:
            parts = key.split('_')
            if len(parts) >= 4:
                batch_id = int(parts[3])
                allocated_qty = Decimal(request.form.get(key) or '0')
                
                if allocated_qty > 0:
                    # Validate batch allocation
                    is_valid, error_msg = BatchAllocationService.validate_batch_allocation(
                        batch_id, item_id, allocated_qty
                    )
                    if not is_valid:
                        raise ValueError(error_msg)
                    
                    # Get batch details for warehouse tracking
                    batch = ItemBatch.query.options(
                        joinedload(ItemBatch.inventory).joinedload(Inventory.warehouse)
                    ).get(batch_id)
                    
                    if not batch:
                        raise ValueError(f'Batch {batch_id} not found')
                    
                    total_allocated += allocated_qty
                    batch_allocations.append((batch_id, batch.inventory_id, allocated_qty, batch.uom_code))
                    
                    # Collect for reservation service (track by warehouse for aggregation)
                    new_allocations.append({
                        'item_id': item_id,
                        'batch_id': batch_id,
                        'warehouse_id': batch.inventory.inventory_id,
                        'allocated_qty': allocated_qty
                    })
        
        # Validate quantity limit using service
        is_valid, error_msg = item_status_service.validate_quantity_limit(
            item_id, total_allocated, request_qty
        )
        if not is_valid:
            raise ValueError(error_msg)
        
        if validate_complete and total_allocated < request_qty:
            raise ValueError(f'Item {item.item.item_name} is not fully allocated ({total_allocated} of {request_qty})')
        
        # Determine the correct status based on allocation
        # CRITICAL: Status must match issue_qty to satisfy database constraints
        if total_allocated == Decimal('0'):
            # No allocation -> Requested
            calculated_status = 'R'
        elif total_allocated >= request_qty:
            # Fully allocated -> Filled
            calculated_status = 'F'
        else:
            # Partially allocated -> Partly Filled
            calculated_status = 'P'
        
        # Get requested status from form, or use calculated status
        form_status = request.form.get(f'status_{item_id}')
        if form_status:
            # Explicit status provided in form (manual override)
            requested_status = form_status
        else:
            # No explicit status - use calculated status
            requested_status = calculated_status
        
        # Get custom reason if provided (for D/L statuses)
        custom_reason = request.form.get(f'status_reason_{item_id}', '').strip()
        
        # Validate status transition using service
        is_valid, error_msg = item_status_service.validate_status_transition(
            item_id,
            item.status_code,
            requested_status,
            total_allocated,
            request_qty
        )
        if not is_valid:
            raise ValueError(error_msg)
        
        # Update relief request item fields - MUST be done atomically
        # Set status first to ensure constraint satisfaction
        item.status_code = requested_status
        
        # Set issue_qty based on status code according to constraint c_reliefrqst_item_2a:
        # - R, U, W, D: issue_qty must be 0
        # - P, L: issue_qty must be < request_qty
        # - F: issue_qty must equal request_qty
        if requested_status in ['R', 'U', 'W', 'D']:
            item.issue_qty = 0
        elif requested_status in ['P', 'L']:
            # Partial fill - use allocated amount (must be < request_qty)
            item.issue_qty = min(total_allocated, item.request_qty - Decimal('0.01'))
        elif requested_status == 'F':
            # Fully filled - must equal request_qty
            item.issue_qty = item.request_qty
        else:
            # Default: set to allocated amount
            item.issue_qty = total_allocated
        
        # Set status_reason_desc for statuses that require it (D, L)
        if requested_status in ['D', 'L']:
            # Use custom reason if provided, otherwise use defaults
            if custom_reason:
                item.status_reason_desc = custom_reason
            elif requested_status == 'L':
                item.status_reason_desc = f'Allocated {total_allocated} of {request_qty} based on available stock'
            elif requested_status == 'D':
                item.status_reason_desc = 'Item denied due to logistics constraints'
        else:
            # Clear reason for other statuses
            item.status_reason_desc = None
        
        # Only set action_by_id when status is NOT 'R' (per constraint c_reliefrqst_item_7)
        if requested_status != 'R':
            item.action_by_id = current_user.user_name
            item.action_dtime = datetime.now()
        else:
            # When status is 'R', action_by_id must be NULL
            item.action_by_id = None
            item.action_dtime = None
        
        item.version_nbr += 1
        
        # Create ReliefPkgItem records for each batch allocation
        for batch_id, inventory_id, allocated_qty, uom_code in batch_allocations:
            if allocated_qty > 0:
                pkg_item = ReliefPkgItem(
                    reliefpkg_id=relief_pkg.reliefpkg_id,
                    fr_inventory_id=inventory_id,
                    item_id=item_id,
                    batch_id=batch_id,  # REQUIRED in new schema
                    item_qty=allocated_qty,
                    uom_code=uom_code,
                    create_by_id=current_user.user_name,
                    create_dtime=datetime.now(),
                    update_by_id=current_user.user_name,
                    update_dtime=datetime.now(),
                    version_nbr=1
                )
                db.session.add(pkg_item)
    
    return new_allocations




@packaging_bp.route('/<int:reliefrqst_id>/cancel', methods=['POST'])
@login_required
def cancel_preparation(reliefrqst_id):
    """
    Cancel package preparation - discards all changes, releases inventory reservations and lock.
    Does NOT save any draft.
    """
    try:
        # Get the relief package for this request (if it exists)
        relief_pkg = ReliefPkg.query.filter_by(reliefrqst_id=reliefrqst_id).first()
        
        if relief_pkg:
            # Delete all relief package items (discard any draft allocations)
            ReliefPkgItem.query.filter_by(reliefpkg_id=relief_pkg.reliefpkg_id).delete()
            db.session.flush()
        
        # Release inventory reservations
        success, error_msg = reservation_service.release_all_reservations(reliefrqst_id)
        if not success:
            flash(f'Warning: Failed to release reservations: {error_msg}', 'warning')
        
        # Release lock
        lock_service.release_lock(reliefrqst_id, current_user.user_id, release_reservations=False)
        
        # Commit the deletion of package items
        db.session.commit()
        
        flash(f'Package preparation for relief request #{reliefrqst_id} has been cancelled', 'info')
        return redirect(url_for('packaging.pending_fulfillment'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error canceling preparation: {str(e)}', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=reliefrqst_id))


@packaging_bp.route('/api/inventory/<int:item_id>/<int:warehouse_id>')
@login_required
def get_inventory(item_id, warehouse_id):
    """API endpoint to get current inventory for an item at a warehouse.
    Note: warehouse_id is stored as inventory_id in the composite PK."""
    inventory = Inventory.query.filter_by(
        item_id=item_id,
        inventory_id=warehouse_id,  # Use inventory_id (which IS the warehouse_id)
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


@packaging_bp.route('/api/item/<int:item_id>/batches')
@login_required
def get_item_batches(item_id):
    """
    API endpoint to get available batches for an item.
    Returns limited batch list (minimum needed to fulfill) with priority groups.
    Supports new drawer workflow requirements.
    """
    try:
        # Get query parameters
        remaining_qty = request.args.get('remaining_qty', type=float)
        required_uom = request.args.get('required_uom', type=str)
        allocated_batch_ids_str = request.args.get('allocated_batch_ids', type=str)
        
        # Parse allocated batch IDs from comma-separated string
        allocated_batch_ids = []
        if allocated_batch_ids_str:
            try:
                allocated_batch_ids = [int(bid) for bid in allocated_batch_ids_str.split(',') if bid.strip()]
            except ValueError:
                pass  # Ignore invalid batch IDs
        
        # Get item to check if it's batched
        item = Item.query.get(item_id)
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        # Use new method to get limited batches if remaining_qty provided
        # Include remaining_qty=0 case for editing existing allocations
        if remaining_qty is not None:
            limited_batches, total_available, shortfall = BatchAllocationService.get_limited_batches_for_drawer(
                item_id,
                Decimal(str(remaining_qty)),
                required_uom,
                allocated_batch_ids
            )
            
            # Assign priority groups
            batch_groups = BatchAllocationService.assign_priority_groups(limited_batches, item)
            
            # Format batches with priority groups
            result = []
            for batch, priority_group in batch_groups:
                available_qty = batch.usable_qty - batch.reserved_qty
                result.append({
                    'batch_id': batch.batch_id,
                    'batch_no': batch.batch_no,
                    'batch_date': batch.batch_date.isoformat() if batch.batch_date else None,
                    'expiry_date': batch.expiry_date.isoformat() if batch.expiry_date else None,
                    'warehouse_id': batch.inventory.inventory_id,
                    'warehouse_name': batch.inventory.warehouse.warehouse_name,
                    'inventory_id': batch.inventory_id,
                    'usable_qty': float(batch.usable_qty),
                    'reserved_qty': float(batch.reserved_qty),
                    'available_qty': float(available_qty),
                    'defective_qty': float(batch.defective_qty),
                    'expired_qty': float(batch.expired_qty),
                    'uom_code': batch.uom_code,
                    'size_spec': batch.size_spec,
                    'is_expired': batch.is_expired,
                    'status_code': batch.status_code,
                    'priority_group': priority_group
                })
            
            return jsonify({
                'item_id': item_id,
                'item_name': item.item_name,
                'is_batched': item.is_batched_flag,
                'can_expire': item.can_expire_flag,
                'issuance_order': item.issuance_order,
                'batches': result,
                'total_available': float(total_available),
                'shortfall': float(shortfall),
                'can_fulfill': shortfall == 0
            })
        else:
            # Legacy mode: return all batches grouped by warehouse (for backward compatibility)
            warehouse_batches = BatchAllocationService.get_batches_by_warehouse(item_id)
            
            result = {}
            for wh_id, batch_list in warehouse_batches.items():
                result[wh_id] = []
                for batch in batch_list:
                    available_qty = batch.usable_qty - batch.reserved_qty
                    result[wh_id].append({
                        'batch_id': batch.batch_id,
                        'batch_no': batch.batch_no,
                        'batch_date': batch.batch_date.isoformat() if batch.batch_date else None,
                        'expiry_date': batch.expiry_date.isoformat() if batch.expiry_date else None,
                        'warehouse_id': batch.inventory.inventory_id,
                        'warehouse_name': batch.inventory.warehouse.warehouse_name,
                        'inventory_id': batch.inventory_id,
                        'usable_qty': float(batch.usable_qty),
                        'reserved_qty': float(batch.reserved_qty),
                        'available_qty': float(available_qty),
                        'defective_qty': float(batch.defective_qty),
                        'expired_qty': float(batch.expired_qty),
                        'uom_code': batch.uom_code,
                        'size_spec': batch.size_spec,
                        'is_expired': batch.is_expired,
                        'status_code': batch.status_code
                    })
            
            return jsonify({
                'item_id': item_id,
                'item_name': item.item_name,
                'is_batched': item.is_batched_flag,
                'can_expire': item.can_expire_flag,
                'issuance_order': item.issuance_order,
                'batches': result
            })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@packaging_bp.route('/api/item/<int:item_id>/auto-allocate', methods=['POST'])
@login_required
def auto_allocate_item(item_id):
    """
    API endpoint to auto-allocate batches for an item using FEFO/FIFO rules.
    
    Expected JSON payload:
    {
        "requested_qty": 100,
        "warehouse_id": 1  # optional
    }
    """
    try:
        data = request.get_json()
        requested_qty = Decimal(str(data.get('requested_qty', 0)))
        warehouse_id = data.get('warehouse_id')
        
        if requested_qty <= 0:
            return jsonify({'error': 'Requested quantity must be greater than zero'}), 400
        
        # Get auto-allocations
        allocations = BatchAllocationService.auto_allocate_batches(
            item_id,
            requested_qty,
            warehouse_id
        )
        
        # Calculate totals
        total_allocated = sum(Decimal(str(a['allocated_qty'])) for a in allocations)
        shortage = requested_qty - total_allocated if total_allocated < requested_qty else Decimal('0')
        
        return jsonify({
            'item_id': item_id,
            'requested_qty': float(requested_qty),
            'total_allocated': float(total_allocated),
            'shortage': float(shortage),
            'allocations': allocations
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@packaging_bp.route('/api/batch/<int:batch_id>')
@login_required
def get_batch_details(batch_id):
    """API endpoint to get detailed information about a specific batch"""
    try:
        batch_details = BatchAllocationService.get_batch_details(batch_id)
        
        if not batch_details:
            return jsonify({'error': 'Batch not found'}), 404
        
        # Convert date objects to ISO format for JSON
        if batch_details.get('batch_date'):
            batch_details['batch_date'] = batch_details['batch_date'].isoformat()
        if batch_details.get('expiry_date'):
            batch_details['expiry_date'] = batch_details['expiry_date'].isoformat()
        
        return jsonify(batch_details)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
