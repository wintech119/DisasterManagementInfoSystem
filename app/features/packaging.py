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
import uuid

from app.db import db
from app.db.models import (
    ReliefRqst, ReliefRqstItem, Item, Warehouse, Inventory, ItemBatch,
    User, Notification,
    ReliefPkg, ReliefPkgItem, ReliefRqstItemStatus
)
from app.core.rbac import has_permission, permission_required
from app.services import relief_request_service as rr_service
from app.services import item_status_service
from app.services import inventory_reservation_service as reservation_service
from app.services.batch_allocation_service import BatchAllocationService
from app.core.audit import add_audit_fields
from app.core.exceptions import OptimisticLockError


def _validate_version_nbr(entity_name, expected_version, actual_version):
    """
    Validate version_nbr for optimistic locking.
    Raises OptimisticLockError if versions don't match.
    
    Args:
        entity_name: User-friendly name of the entity (e.g., "relief request", "package")
        expected_version: Version sent from UI
        actual_version: Current version in database
    """
    if expected_version is None:
        raise OptimisticLockError(f"Version number is required for {entity_name}")
    
    if int(expected_version) != int(actual_version):
        raise OptimisticLockError(
            f"This {entity_name} has been updated by another user. Please refresh the page and try again."
        )


packaging_bp = Blueprint('packaging', __name__, url_prefix='/packaging')


@packaging_bp.route('/pending-approval')
@login_required
def pending_approval():
    """
    LM approval queue - shows packages submitted by LO awaiting LM approval.
    
    Criteria for "Pending LM Approval":
    - Relief Request status = SUBMITTED or PART_FILLED (allows multi-batch fulfillment)
    - ReliefPkg exists with status_code='P' (Pending - submitted for approval)
    - Not yet dispatched (dispatch_dtime is NULL)
    
    Concurrency control is handled via optimistic locking (version_nbr).
    """
    from app.core.rbac import is_logistics_manager
    if not is_logistics_manager():
        flash('Access denied. Only Logistics Managers can view this page.', 'danger')
        abort(403)
    
    # Find all relief requests with packages awaiting LM approval
    # IMPORTANT: Include both SUBMITTED and PART_FILLED to support multi-batch fulfillment
    # (After first dispatch, status becomes PART_FILLED but may need additional batches)
    all_requests = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.packages)
    ).filter(
        ReliefRqst.status_code.in_([rr_service.STATUS_SUBMITTED, rr_service.STATUS_PART_FILLED])
    ).order_by(ReliefRqst.create_dtime.desc()).all()
    
    # Filter to requests with packages pending LM approval
    # Package must have: status='P', verify_by_id!=NULL (submitted, not draft), dispatch_dtime=NULL (not dispatched)
    pending_requests = []
    for req in all_requests:
        # Check if there's a ReliefPkg submitted for approval (verify_by_id is set)
        relief_pkg = next((pkg for pkg in req.packages 
                          if pkg.status_code == rr_service.PKG_STATUS_PENDING 
                          and pkg.verify_by_id is not None  # Only submitted packages (not drafts)
                          and pkg.dispatch_dtime is None), None)
        
        if relief_pkg:
            # Package exists and is submitted for approval (not just a draft)
            pending_requests.append(req)
    
    counts = {
        'pending_approval': len(pending_requests)
    }
    
    return render_template('packaging/pending_approval.html',
                         requests=pending_requests,
                         counts=counts,
                         STATUS_SUBMITTED=rr_service.STATUS_SUBMITTED,
                         STATUS_PART_FILLED=rr_service.STATUS_PART_FILLED,
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
            # fr_inventory_id IS the warehouse_id (inventory_id = warehouse_id in schema)
            warehouse_id = pkg_item.fr_inventory_id
            
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
            # CRITICAL VALIDATION: Ensure package has items AND issue_qty matches ReliefPkgItem totals
            # Get all ReliefPkgItem records for this package
            pkg_items = ReliefPkgItem.query.filter_by(reliefpkg_id=relief_pkg.reliefpkg_id).all()
            
            if not pkg_items:
                # No items allocated - package is empty
                # Check if all items have valid unavailability statuses (U, D, W)
                unavailability_statuses = {'U', 'D', 'W'}
                all_items_unavailable = all(
                    item.status_code in unavailability_statuses 
                    for item in relief_request.items
                )
                
                if not all_items_unavailable:
                    raise ValueError('Cannot dispatch package: no items have been allocated. All requested items must either have batch allocations or be marked as Unavailable (U), Denied (D), or Awaiting Availability (W).')
            
            # Validate that ReliefPkgItem quantities match issue_qty for data integrity
            # Build totals from ReliefPkgItem records
            pkg_item_totals = {}
            for pkg_item in pkg_items:
                if pkg_item.item_id not in pkg_item_totals:
                    pkg_item_totals[pkg_item.item_id] = Decimal('0')
                pkg_item_totals[pkg_item.item_id] += pkg_item.item_qty
            
            # Verify each item's issue_qty matches ReliefPkgItem total
            for item in relief_request.items:
                pkg_total = pkg_item_totals.get(item.item_id, Decimal('0'))
                
                # For items with issue_qty > 0, must have matching ReliefPkgItem records
                if item.issue_qty > 0 and pkg_total == Decimal('0'):
                    raise ValueError(f'Data integrity error: Item {item.item.item_name} has issue_qty={item.issue_qty} but no package items allocated. Please re-prepare the package.')
                
                # Verify totals match (allowing small decimal precision differences)
                if abs(item.issue_qty - pkg_total) > Decimal('0.001'):
                    raise ValueError(f'Data integrity error: Item {item.item.item_name} issue_qty ({item.issue_qty}) does not match allocated quantity ({pkg_total}). Please re-prepare the package.')
            
            # Verify at least one item has allocated quantity (support partial fulfillment)
            # UNLESS all items are marked as unavailable (U, D, W)
            has_allocated_items = any(item.issue_qty > 0 for item in relief_request.items)
            
            if not has_allocated_items:
                # Check if all items have valid unavailability statuses
                unavailability_statuses = {'U', 'D', 'W'}
                all_items_unavailable = all(
                    item.status_code in unavailability_statuses 
                    for item in relief_request.items
                )
                
                if not all_items_unavailable:
                    # Items have no allocations AND not all marked unavailable
                    raise ValueError('Cannot dispatch empty package. Please allocate items before dispatching or mark all items as unavailable.')
            
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


@packaging_bp.route('/<int:reliefrqst_id>/approve', methods=['GET', 'POST'])
@login_required
def approve_package(reliefrqst_id):
    """
    LM approves package with full editing capability.
    Similar to prepare_package but:
    - LM-only access
    - Loads existing allocations from pending package
    - Allows editing with batch drawer (FEFO/FIFO logic)
    - Save Draft or Approve & Dispatch
    """
    from app.core.rbac import is_logistics_manager
    if not is_logistics_manager():
        flash('Access denied. Only Logistics Managers can approve packages.', 'danger')
        abort(403)
    
    relief_request = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.category),
        joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.default_uom),
        joinedload(ReliefRqst.packages)
    ).get_or_404(reliefrqst_id)
    
    # Get the pending package
    relief_pkg = next((pkg for pkg in relief_request.packages if pkg.status_code == rr_service.PKG_STATUS_PENDING), None)
    
    if not relief_pkg:
        flash('No pending package found for this relief request.', 'danger')
        return redirect(url_for('packaging.pending_approval'))
    
    if relief_pkg.dispatch_dtime is not None:
        flash('This package has already been dispatched.', 'warning')
        return redirect(url_for('packaging.pending_approval'))
    
    if request.method == 'GET':
        
        # Load warehouses
        warehouses = Warehouse.query.filter_by(status_code='A').order_by(Warehouse.warehouse_name).all()
        
        # Load inventory availability for each item
        item_inventory_map = {}
        for item in relief_request.items:
            inventories = Inventory.query.filter_by(
                item_id=item.item_id,
                status_code='A'
            ).filter(
                Inventory.usable_qty > 0
            ).join(Warehouse).order_by(Warehouse.warehouse_name).all()
            
            item_inventory_map[item.item_id] = inventories
        
        # Load existing BATCH-LEVEL allocations from the pending package
        # This ensures LM sees LO's prepared allocations exactly as submitted
        existing_batch_allocations = {}
        for pkg_item in relief_pkg.items:
            item_id = pkg_item.item_id
            warehouse_id = pkg_item.fr_inventory_id  # fr_inventory_id IS the warehouse_id
            batch_id = pkg_item.batch_id
            
            if item_id not in existing_batch_allocations:
                existing_batch_allocations[item_id] = []
            
            # Store batch-level allocation details
            existing_batch_allocations[item_id].append({
                'warehouse_id': warehouse_id,
                'batch_id': batch_id,
                'qty': float(pkg_item.item_qty)  # Convert Decimal to float for JSON
            })
        
        # Load item status map
        status_map = item_status_service.load_status_map()
        
        # Compute item status options
        item_status_options = {}
        for item in relief_request.items:
            total_allocated = Decimal('0')
            if item.item_id in existing_batch_allocations:
                for batch_allocation in existing_batch_allocations[item.item_id]:
                    total_allocated += Decimal(str(batch_allocation['qty']))
            
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
        
        return render_template('packaging/approve.html',
                             relief_request=relief_request,
                             relief_pkg=relief_pkg,
                             warehouses=warehouses,
                             item_inventory_map=item_inventory_map,
                             existing_batch_allocations=existing_batch_allocations,
                             status_map=status_map,
                             item_status_options=item_status_options)
    
    # POST: Handle actions
    
    action = request.form.get('action')
    
    # Extract version numbers for optimistic locking
    relief_request_version = request.form.get('relief_request_version')
    package_version = request.form.get('package_version')
    
    if action == 'save_draft':
        return _save_draft_approval(relief_request, relief_pkg, relief_request_version, package_version)
    elif action == 'approve_and_dispatch':
        return _approve_and_dispatch(relief_request, relief_pkg, relief_request_version, package_version)
    else:
        flash('Invalid action', 'danger')
        return redirect(url_for('packaging.approve_package', reliefrqst_id=reliefrqst_id))


def _save_draft_approval(relief_request, relief_pkg, relief_request_version, package_version):
    """
    LM saves draft changes during approval workflow.
    
    Draft behavior:
    - Updates allocations with delta-based itembatch changes
    - Keeps package in Pending status with verify_by_id set (indicates submitted for approval)
    - Package stays in "Awaiting Approval" queue for continued LM editing
    - No notifications sent
    - Concurrency control via optimistic locking (version_nbr)
    """
    try:
        # OPTIMISTIC LOCKING: Validate relief request version
        _validate_version_nbr("relief request", relief_request_version, relief_request.version_nbr)
        
        # OPTIMISTIC LOCKING: Validate package version
        _validate_version_nbr("package", package_version, relief_pkg.version_nbr)
        
        # Process batch allocations and update ReliefPkgItem
        new_allocations = _process_allocations(relief_request, validate_complete=False)
        
        # Keep package in pending status
        relief_pkg.status_code = rr_service.PKG_STATUS_PENDING
        relief_pkg.update_by_id = current_user.user_name
        relief_pkg.update_dtime = datetime.now()
        relief_pkg.version_nbr += 1
        
        # Flush to persist allocations before reservation
        db.session.flush()
        
        # Update inventory reservations with delta-based changes
        old_allocations = relief_request._old_allocations if hasattr(relief_request, '_old_allocations') else {}
        success, error_msg = reservation_service.reserve_inventory(
            relief_request.reliefrqst_id,
            new_allocations,
            old_allocations
        )
        
        if not success:
            # Reservation failed - rollback
            db.session.rollback()
            flash(f'{error_msg}', 'warning')
            flash('Draft not saved due to insufficient inventory.', 'info')
            return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))
        
        # Commit changes
        db.session.commit()
        
        flash(f'Draft saved for relief request #{relief_request.reliefrqst_id}.', 'success')
        
        # Redirect back to approval page so LM can continue editing
        return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))
        
    except OptimisticLockError as e:
        db.session.rollback()
        flash(str(e), 'warning')
        return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving draft: {str(e)}', 'danger')
        return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))


def _approve_and_dispatch(relief_request, relief_pkg, relief_request_version, package_version):
    """
    LM approves package and dispatches to Inventory Clerk.
    - Validates allocations
    - Updates reliefrqst_item.issue_qty
    - Commits inventory (reserved -> actual deduction)
    - Transitions to Dispatched status
    - Notifies Inventory Clerk
    - Releases lock
    """
    try:
        # OPTIMISTIC LOCKING: Validate relief request version
        _validate_version_nbr("relief request", relief_request_version, relief_request.version_nbr)
        
        # OPTIMISTIC LOCKING: Validate package version
        _validate_version_nbr("package", package_version, relief_pkg.version_nbr)
        
        # Process and validate allocations (can be partial)
        new_allocations = _process_allocations(relief_request, validate_complete=False)
        
        # CRITICAL VALIDATION: Ensure package has items AND issue_qty matches ReliefPkgItem totals
        # Get all ReliefPkgItem records for this package
        pkg_items = ReliefPkgItem.query.filter_by(reliefpkg_id=relief_pkg.reliefpkg_id).all()
        
        if not pkg_items:
            # No items allocated - package is empty
            # Check if all items have valid unavailability statuses (U, D, W)
            unavailability_statuses = {'U', 'D', 'W'}
            all_items_unavailable = all(
                item.status_code in unavailability_statuses 
                for item in relief_request.items
            )
            
            if not all_items_unavailable:
                raise ValueError('Cannot dispatch package: no items have been allocated. All requested items must either have batch allocations or be marked as Unavailable (U), Denied (D), or Awaiting Availability (W).')
        
        # Validate that ReliefPkgItem quantities match issue_qty for data integrity
        # Build totals from ReliefPkgItem records
        pkg_item_totals = {}
        for pkg_item in pkg_items:
            if pkg_item.item_id not in pkg_item_totals:
                pkg_item_totals[pkg_item.item_id] = Decimal('0')
            pkg_item_totals[pkg_item.item_id] += pkg_item.item_qty
        
        # Verify each item's issue_qty matches ReliefPkgItem total
        for item in relief_request.items:
            pkg_total = pkg_item_totals.get(item.item_id, Decimal('0'))
            
            # For items with issue_qty > 0, must have matching ReliefPkgItem records
            if item.issue_qty > 0 and pkg_total == Decimal('0'):
                raise ValueError(f'Data integrity error: Item {item.item.item_name} has issue_qty={item.issue_qty} but no package items allocated. Please re-prepare the package.')
            
            # Verify totals match (allowing small decimal precision differences)
            if abs(item.issue_qty - pkg_total) > Decimal('0.001'):
                raise ValueError(f'Data integrity error: Item {item.item.item_name} issue_qty ({item.issue_qty}) does not match allocated quantity ({pkg_total}). Please re-prepare the package.')
        
        # Verify at least one item has allocated quantity (support partial fulfillment)
        # UNLESS all items are marked as unavailable (U, D, W)
        has_allocated_items = any(alloc['allocated_qty'] > 0 for alloc in new_allocations)
        
        if not has_allocated_items:
            # Check if all items have valid unavailability statuses
            unavailability_statuses = {'U', 'D', 'W'}
            all_items_unavailable = all(
                item.status_code in unavailability_statuses 
                for item in relief_request.items
            )
            
            if not all_items_unavailable:
                # Items have no allocations AND not all marked unavailable
                raise ValueError('Cannot dispatch empty package. Please allocate items before dispatching or mark all items as unavailable.')
        
        # Update issue_qty for each item based on total allocated quantity
        for item in relief_request.items:
            total_allocated = Decimal('0')
            for alloc in new_allocations:
                if alloc['item_id'] == item.item_id:
                    total_allocated += alloc['allocated_qty']
            
            item.issue_qty = total_allocated
            item.version_nbr += 1
        
        # LM approval: set verify_by_id and verify_dtime
        relief_pkg.verify_by_id = current_user.user_name
        relief_pkg.verify_dtime = datetime.now()
        
        # Mark package as dispatched
        relief_pkg.status_code = rr_service.PKG_STATUS_DISPATCHED
        relief_pkg.dispatch_dtime = datetime.now()
        relief_pkg.update_by_id = current_user.user_name
        relief_pkg.update_dtime = datetime.now()
        relief_pkg.version_nbr += 1
        
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
        
        # Notify Inventory Clerk and agency users
        try:
            from app.services.notification_service import NotificationService
            
            # Notify logistics officers (inventory clerks)
            lo_users = NotificationService.get_active_users_by_role_codes(['LOGISTICS_OFFICER', 'INVENTORY_CLERK'])
            
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
        return redirect(url_for('packaging.transaction_summary', reliefpkg_id=relief_pkg.reliefpkg_id))
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))
    except OptimisticLockError as e:
        db.session.rollback()
        flash(f'Concurrency conflict: {str(e)} Please refresh the page and try again.', 'danger')
        return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving package: {str(e)}', 'danger')
        return redirect(url_for('packaging.approve_package', reliefrqst_id=relief_request.reliefrqst_id))


@packaging_bp.route('/transaction-summary/<int:reliefpkg_id>')
@login_required
def transaction_summary(reliefpkg_id):
    """
    Display print-friendly transaction summary after LM approval.
    Shows all package details, allocations by warehouse/batch, and signature section.
    """
    from app.core.rbac import is_logistics_manager, is_logistics_officer
    if not (is_logistics_manager() or is_logistics_officer()):
        flash('Access denied. Only Logistics Officers and Managers can view transaction summaries.', 'danger')
        abort(403)
    
    # Get the tab the user came from (for proper back navigation)
    from_tab = request.args.get('from_tab', 'approved_for_dispatch')
    
    # Load package with all related data
    relief_pkg = ReliefPkg.query.options(
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.default_uom),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item_status),
        joinedload(ReliefPkg.items)
    ).get_or_404(reliefpkg_id)
    
    # Get package creator and approver info
    creator = User.query.filter_by(user_name=relief_pkg.create_by_id).first() if relief_pkg.create_by_id else None
    approver = User.query.filter_by(user_name=relief_pkg.verify_by_id).first() if relief_pkg.verify_by_id else None
    
    # Organize items by batch with warehouse info
    items_with_batches = []
    for req_item in relief_pkg.relief_request.items:
        # Get all package items (batches) for this request item
        pkg_items = [pi for pi in relief_pkg.items if pi.item_id == req_item.item_id]
        
        batches_info = []
        for pkg_item in pkg_items:
            # Load batch and warehouse info
            batch = ItemBatch.query.get(pkg_item.batch_id) if pkg_item.batch_id else None
            warehouse = Warehouse.query.get(pkg_item.fr_inventory_id) if pkg_item.fr_inventory_id else None
            
            batches_info.append({
                'warehouse_name': warehouse.warehouse_name if warehouse else 'Unknown',
                'batch_no': batch.batch_no if batch else 'N/A',
                'batch_date': batch.batch_date if batch else None,
                'expiry_date': batch.expiry_date if batch else None,
                'qty': pkg_item.item_qty
            })
        
        total_issued = sum(b['qty'] for b in batches_info)
        
        items_with_batches.append({
            'item': req_item.item,
            'requested_qty': req_item.request_qty,
            'issued_qty': total_issued,
            'batches': batches_info,
            'status_code': req_item.status_code,
            'status_desc': req_item.item_status.status_desc if req_item.item_status else None,
            'status_reason': req_item.status_reason_desc
        })
    
    # Calculate summary totals
    total_items = len(items_with_batches)
    total_batches = sum(len(item['batches']) for item in items_with_batches)
    unique_warehouses = set()
    for item in items_with_batches:
        for batch in item['batches']:
            unique_warehouses.add(batch['warehouse_name'])
    warehouses_used = len(unique_warehouses)
    
    return render_template('packaging/transaction_summary.html',
                         relief_pkg=relief_pkg,
                         relief_request=relief_pkg.relief_request,
                         items_with_batches=items_with_batches,
                         creator=creator,
                         approver=approver,
                         total_items=total_items,
                         total_batches=total_batches,
                         warehouses_used=warehouses_used,
                         generated_at=datetime.now(),
                         from_tab=from_tab)


@packaging_bp.route('/create-request-on-behalf', methods=['GET', 'POST'])
@login_required
def create_request_on_behalf():
    """
    Create relief request on behalf of an agency.
    - Logistics Officers/Managers: Can select any agency
    - Agency Users: Automatically use their own agency
    """
    from app.core.rbac import is_logistics_officer, is_logistics_manager, is_agency_user
    from app.db.models import Agency, Event
    
    # Allow logistics users and agency users
    is_logistics = is_logistics_officer() or is_logistics_manager()
    is_agency = is_agency_user()
    
    if not (is_logistics or is_agency):
        flash('Access denied.', 'danger')
        abort(403)
    
    if request.method == 'POST':
        try:
            # Agency users use their own agency; logistics users select from dropdown
            if is_agency:
                agency_id = current_user.agency_id
                if not agency_id:
                    flash('Your user account is not associated with an agency.', 'danger')
                    return redirect(url_for('packaging.create_request_on_behalf'))
            else:
                # Logistics users select agency
                agency_id = request.form.get('agency_id')
                if not agency_id:
                    flash('Please select an agency', 'danger')
                    return redirect(url_for('packaging.create_request_on_behalf'))
                agency_id = int(agency_id)
            
            urgency_ind = request.form.get('urgency_ind', 'M')
            eligible_event_id = request.form.get('eligible_event_id')
            eligible_event_id = int(eligible_event_id) if eligible_event_id else None
            rqst_notes_text = request.form.get('rqst_notes_text', '').strip()
            
            # Validate agency
            agency = Agency.query.get(agency_id)
            if not agency:
                flash('Invalid agency selected', 'danger')
                return redirect(url_for('packaging.create_request_on_behalf'))
            
            # Validate urgency
            if urgency_ind not in ['H', 'M', 'L']:
                flash('Invalid urgency level', 'danger')
                return redirect(url_for('packaging.create_request_on_behalf'))
            
            # Create draft request using existing service
            relief_request = rr_service.create_draft_request(
                agency_id=agency_id,
                urgency_ind=urgency_ind,
                eligible_event_id=eligible_event_id,
                rqst_notes_text=rqst_notes_text,
                user_email=current_user.email
            )
            
            db.session.commit()
            
            flash(f'Draft relief request #{relief_request.reliefrqst_id} created successfully for {agency.agency_name}. Add items to continue.', 'success')
            # Redirect to the standard edit_items page in requests blueprint
            return redirect(url_for('requests.edit_items', request_id=relief_request.reliefrqst_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating request: {str(e)}', 'danger')
            return redirect(url_for('packaging.create_request_on_behalf'))
    
    # GET request - show form
    events = Event.query.filter_by(status_code='A').order_by(Event.start_date.desc()).all()
    
    # For agency users, get their agency; for logistics, get all agencies
    if is_agency:
        user_agency = Agency.query.get(current_user.agency_id) if current_user.agency_id else None
        agencies = None  # Don't show agency selector for agency users
    else:
        user_agency = None
        agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
    
    return render_template('packaging/create_request_on_behalf.html',
                         agencies=agencies,
                         user_agency=user_agency,
                         is_logistics=is_logistics,
                         events=events,
                         today=date.today().isoformat())


@packaging_bp.route('/pending-fulfillment')
@login_required
def pending_fulfillment():
    """
    List all approved relief requests awaiting package preparation.
    Shows SUBMITTED (3) and PART_FILLED (5) requests for LO/LM to fulfill.
    Also shows approved packages (status='D') for informational purposes.
    """
    from app.core.rbac import is_logistics_officer, is_logistics_manager
    if not (is_logistics_officer() or is_logistics_manager()):
        flash('Access denied. Only Logistics Officers and Managers can view this page.', 'danger')
        abort(403)
    
    filter_type = request.args.get('filter', 'awaiting')
    
    # Handle approved_for_dispatch filter - shows approved packages WITH items allocated
    if filter_type == 'approved_for_dispatch':
        # Query approved packages (status='D') with items allocated
        approved_packages = ReliefPkg.query.options(
            joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
            joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.eligible_event),
            joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.item)
        ).filter(
            ReliefPkg.status_code == rr_service.PKG_STATUS_DISPATCHED
        ).order_by(ReliefPkg.dispatch_dtime.desc()).all()
        
        # Filter to only packages WITH items allocated AND user should see them
        current_user_name = current_user.user_name
        package_data = []
        for pkg in approved_packages:
            item_count = len(pkg.items)
            
            # Determine if user should see this package
            if is_logistics_manager():
                # LM: Can see all packages
                user_should_see = True
            else:
                # LO: Can see packages they created/updated OR relief requests they created
                user_should_see = (
                    pkg.create_by_id == current_user_name or 
                    pkg.update_by_id == current_user_name or
                    (pkg.relief_request and pkg.relief_request.create_by_id == current_user_name)
                )
            
            if item_count > 0 and user_should_see:  # Only packages with allocated items AND user can see
                package_data.append({
                    'package': pkg,
                    'relief_request': pkg.relief_request,
                    'item_count': item_count,
                    'total_qty': sum(item.item_qty for item in pkg.items if item.item_qty)
                })
        
        # Count approved packages with items (user-specific or all for LM)
        total_approved = len(package_data)
        awaiting_handover = len([p['package'] for p in package_data if not p['package'].received_dtime])
        
        # Count packages with no allocation for global counts
        if is_logistics_manager():
            # LM: Count all packages with no allocation
            approved_no_allocation_count = len([pkg for pkg in approved_packages if len(pkg.items) == 0])
        else:
            # LO: Count only their packages with no allocation (or relief requests they created)
            approved_no_allocation_count = len([pkg for pkg in approved_packages 
                                               if len(pkg.items) == 0 
                                               and (pkg.create_by_id == current_user_name or 
                                                    pkg.update_by_id == current_user_name or
                                                    (pkg.relief_request and pkg.relief_request.create_by_id == current_user_name))])
        
        return render_template('packaging/pending_fulfillment.html',
                             requests=[],
                             packages=package_data,
                             counts={'approved': total_approved, 'awaiting_handover': awaiting_handover},
                             global_counts={'approved': total_approved, 'approved_no_allocation': approved_no_allocation_count},
                             current_filter=filter_type,
                             now=datetime.now())
    
    # Handle approved_no_allocation filter - shows approved packages WITHOUT items allocated
    if filter_type == 'approved_no_allocation':
        # Query all approved packages (status='D')
        all_approved_packages = ReliefPkg.query.options(
            joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
            joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.eligible_event),
            joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.items),
            joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.item)
        ).filter(
            ReliefPkg.status_code == rr_service.PKG_STATUS_DISPATCHED
        ).order_by(ReliefPkg.dispatch_dtime.desc()).all()
        
        # Filter to only packages WITHOUT items allocated AND user should see them
        current_user_name = current_user.user_name
        package_data = []
        for pkg in all_approved_packages:
            # Determine if user should see this package
            if is_logistics_manager():
                # LM: Can see all packages
                user_should_see = True
            else:
                # LO: Can see packages they created/updated OR relief requests they created
                user_should_see = (
                    pkg.create_by_id == current_user_name or 
                    pkg.update_by_id == current_user_name or
                    (pkg.relief_request and pkg.relief_request.create_by_id == current_user_name)
                )
            
            if len(pkg.items) == 0 and user_should_see:  # Only packages with NO allocated items AND user can see
                package_data.append({
                    'package': pkg,
                    'relief_request': pkg.relief_request,
                    'item_count': 0,
                    'total_qty': 0
                })
        
        # Count packages with no allocation (user-specific or all for LM)
        total_no_allocation = len(package_data)
        
        # Count packages with items for global counts
        if is_logistics_manager():
            # LM: Count all packages with items
            approved_with_items_count = len([pkg for pkg in all_approved_packages if len(pkg.items) > 0])
        else:
            # LO: Count only their packages with items (or relief requests they created)
            approved_with_items_count = len([pkg for pkg in all_approved_packages 
                                            if len(pkg.items) > 0 
                                            and (pkg.create_by_id == current_user_name or 
                                                 pkg.update_by_id == current_user_name or
                                                 (pkg.relief_request and pkg.relief_request.create_by_id == current_user_name))])
        
        return render_template('packaging/pending_fulfillment.html',
                             requests=[],
                             packages=package_data,
                             counts={'approved_no_allocation': total_no_allocation},
                             global_counts={'approved': approved_with_items_count, 'approved_no_allocation': total_no_allocation},
                             current_filter=filter_type,
                             now=datetime.now())
    
    # Normal request-based filters
    base_query = ReliefRqst.query.options(
        joinedload(ReliefRqst.agency),
        joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefRqst.status),
        joinedload(ReliefRqst.items),
        joinedload(ReliefRqst.packages)  # Load packages to check for pending approval
    ).filter(
        ReliefRqst.status_code.in_([rr_service.STATUS_SUBMITTED, rr_service.STATUS_PART_FILLED])
    ).order_by(ReliefRqst.create_dtime.desc())
    
    all_requests = base_query.all()
    
    # Helper function to check if request has package pending LM approval
    def has_pending_approval(req):
        """
        Check if request has a package submitted for LM approval.
        
        Differentiates between:
        - Draft packages: request status=SUBMITTED, package status='P', dispatch_dtime=NULL (shows in "Being Prepared")
        - Submitted packages: request status=PART_FILLED, package status='P', dispatch_dtime=NULL (shows in "Awaiting Approval")
        
        Key insight: When LO submits for approval, relief request status changes to PART_FILLED (line 1347)
        """
        return (req.status_code == rr_service.STATUS_PART_FILLED and
                any(pkg.status_code == rr_service.PKG_STATUS_PENDING 
                    and pkg.dispatch_dtime is None
                    for pkg in req.packages))
    
    # Helper function to check if request has dispatched packages
    def has_dispatched_package(req):
        """
        Check if request has any packages that have been approved and dispatched.
        Dispatched packages should only appear in the "Approved for Dispatch" tab.
        """
        return any(pkg.status_code == rr_service.PKG_STATUS_DISPATCHED 
                   for pkg in req.packages)
    
    # Helper function to check if current user has worked on this request
    def is_user_involved(req):
        """
        Check if the current user should see this request.
        
        For Logistics Officers (LO):
        - Shows packages the LO created or updated
        - Shows packages tied to relief requests the LO created
        
        For Logistics Managers (LM):
        - Shows ALL packages from all LOs and themselves
        - Shows packages they verified or are awaiting their approval
        """
        current_user_name = current_user.user_name
        
        # LM: Can see all packages from all LOs and themselves
        if is_logistics_manager():
            # If request has any packages, LM can see it
            return len(req.packages) > 0
        
        # LO: Can see packages they created/updated OR relief requests they created
        for pkg in req.packages:
            if (pkg.create_by_id == current_user_name or 
                pkg.update_by_id == current_user_name or
                req.create_by_id == current_user_name):
                return True
        
        return False
    
    if filter_type == 'awaiting':
        # Show all SUBMITTED requests (not yet partially filled)
        # Exclude requests with dispatched packages (they belong in Approved for Dispatch tab)
        filtered_requests = [r for r in all_requests 
                           if r.status_code == rr_service.STATUS_SUBMITTED 
                           and not has_pending_approval(r)
                           and not has_dispatched_package(r)]
    elif filter_type == 'in_progress':
        # Being Prepared: Show PART_FILLED requests (in active preparation)
        # Exclude requests with dispatched packages (they belong in Approved for Dispatch tab)
        filtered_requests = [r for r in all_requests 
                           if r.status_code == rr_service.STATUS_PART_FILLED
                           and not has_pending_approval(r)
                           and not has_dispatched_package(r)]
    elif filter_type == 'pending_approval':
        # Show only requests with packages awaiting LM approval AND user is involved
        filtered_requests = [r for r in all_requests if has_pending_approval(r) and is_user_involved(r)]
    else:
        # "All" tab: Show only requests where current user is involved
        filtered_requests = [r for r in all_requests if is_user_involved(r)]
    
    # Count approved packages for the tabs
    # Get all approved packages and split by allocation status
    all_approved_pkgs = ReliefPkg.query.options(
        joinedload(ReliefPkg.items)
    ).filter(
        ReliefPkg.status_code == rr_service.PKG_STATUS_DISPATCHED
    ).all()
    
    approved_with_items = len([pkg for pkg in all_approved_pkgs if len(pkg.items) > 0])
    approved_no_allocation = len([pkg for pkg in all_approved_pkgs if len(pkg.items) == 0])
    
    # For LOs: Filter approved packages by user involvement
    current_user_name = current_user.user_name
    if is_logistics_manager():
        # LM sees all packages
        user_approved_pkgs = all_approved_pkgs
    else:
        # LO sees only packages they created or updated
        user_approved_pkgs = [pkg for pkg in all_approved_pkgs 
                             if pkg.create_by_id == current_user_name or pkg.update_by_id == current_user_name]
    
    user_approved_with_items = len([pkg for pkg in user_approved_pkgs if len(pkg.items) > 0])
    user_approved_no_allocation = len([pkg for pkg in user_approved_pkgs if len(pkg.items) == 0])
    
    # For badge counts: Use user-involved requests (all requests the user should see)
    # This ensures badge counts are correct regardless of which tab is active
    user_requests = [r for r in all_requests if is_user_involved(r)]
    
    global_counts = {
        'submitted': len([r for r in all_requests 
                         if r.status_code == rr_service.STATUS_SUBMITTED 
                         and not has_pending_approval(r)
                         and not has_dispatched_package(r)]),
        'in_progress': len([r for r in all_requests 
                           if r.status_code == rr_service.STATUS_PART_FILLED
                           and not has_pending_approval(r)
                           and not has_dispatched_package(r)]),
        'pending_approval': len([r for r in all_requests if has_pending_approval(r)]),
        'approved': approved_with_items,
        'approved_no_allocation': approved_no_allocation
    }
    
    # Calculate user-scoped counts from ALL user requests (not just filtered by current tab)
    # This ensures badge counts show correct numbers on all tabs
    filtered_counts = {
        'submitted': len([r for r in user_requests 
                         if r.status_code == rr_service.STATUS_SUBMITTED 
                         and not has_pending_approval(r)
                         and not has_dispatched_package(r)]),
        'in_progress': len([r for r in user_requests 
                           if r.status_code == rr_service.STATUS_PART_FILLED
                           and not has_pending_approval(r)
                           and not has_dispatched_package(r)]),
        'pending_approval': len([r for r in user_requests if has_pending_approval(r)]),
        'approved': user_approved_with_items,
        'approved_no_allocation': user_approved_no_allocation
    }
    
    return render_template('packaging/pending_fulfillment.html',
                         requests=filtered_requests,
                         packages=[],
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
        joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item).joinedload(Item.default_uom)
    ).get_or_404(reliefrqst_id)
    
    if relief_request.status_code not in [rr_service.STATUS_SUBMITTED, rr_service.STATUS_PART_FILLED]:
        flash(f'Only SUBMITTED or PART FILLED requests can be packaged. Current status: {relief_request.status.status_desc}', 'danger')
        return redirect(url_for('packaging.pending_fulfillment'))
    
    # ACCESS CONTROL: Check if package has been submitted for LM approval
    # A package is "submitted for LM approval" when it matches has_pending_approval() logic:
    # 1. Relief request status is PART_FILLED (submission or draft in progress)
    # 2. Package status is PENDING ('P')
    # 3. Package has dispatch_dtime = NULL (not yet dispatched by LM)
    # 4. Package was updated (update_by_id is set, indicating LO touched it after initial creation)
    #
    # This differentiates from new drafts which have:
    # - status='P' but update_by_id might be NULL or same as create_by_id
    # - OR relief request is still SUBMITTED (not PART_FILLED)
    existing_package = ReliefPkg.query.filter_by(reliefrqst_id=reliefrqst_id).first()
    is_submitted_for_approval = (
        existing_package and
        relief_request.status_code == rr_service.STATUS_PART_FILLED and
        existing_package.status_code == rr_service.PKG_STATUS_PENDING and
        existing_package.dispatch_dtime is None and
        existing_package.update_by_id is not None and
        existing_package.update_by_id != existing_package.create_by_id  # Differentiates from brand new package
    )
    is_read_only_for_lo = is_submitted_for_approval and is_logistics_officer() and not is_logistics_manager()
    
    if is_read_only_for_lo and request.method == 'POST':
        # LO trying to POST to a submitted package - block it
        flash('This relief request package has already been submitted and is awaiting approval from the Logistics Manager.', 'warning')
        return redirect(url_for('packaging.pending_fulfillment'))
    
    if request.method == 'GET':
        
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
        
        # Get existing package for this relief request (should only be one)
        # Note: existing_package already loaded above for access control check
        existing_packages = [existing_package] if existing_package else []
        
        existing_allocations = {}
        existing_batch_allocations = {}
        for pkg in existing_packages:
            for pkg_item in pkg.items:
                item_id = pkg_item.item_id
                # fr_inventory_id IS the warehouse_id (inventory_id = warehouse_id in schema)
                warehouse_id = pkg_item.fr_inventory_id
                batch_id = pkg_item.batch_id
                
                # Warehouse-level aggregation (for backward compatibility)
                if item_id not in existing_allocations:
                    existing_allocations[item_id] = {}
                
                if warehouse_id not in existing_allocations[item_id]:
                    existing_allocations[item_id][warehouse_id] = Decimal('0')
                
                existing_allocations[item_id][warehouse_id] += pkg_item.item_qty
                
                # Batch-level allocations (for drawer persistence)
                if item_id not in existing_batch_allocations:
                    existing_batch_allocations[item_id] = []
                
                existing_batch_allocations[item_id].append({
                    'warehouse_id': warehouse_id,
                    'batch_id': batch_id,
                    'qty': float(pkg_item.item_qty)  # Convert Decimal to float for JSON
                })
        
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
                             existing_package=existing_package,
                             warehouses=warehouses,
                             item_inventory_map=item_inventory_map,
                             existing_allocations=existing_allocations,
                             existing_batch_allocations=existing_batch_allocations,
                             status_map=status_map,
                             item_status_options=item_status_options,
                             is_read_only=is_read_only_for_lo)
    
    action = request.form.get('action')
    
    # Extract version numbers for optimistic locking
    relief_request_version = request.form.get('relief_request_version')
    package_version = request.form.get('package_version')
    
    if action == 'save_draft':
        return _save_draft(relief_request, relief_request_version, package_version)
    elif action == 'submit_for_approval':
        return _submit_for_approval(relief_request, relief_request_version, package_version)
    elif action == 'send_for_dispatch':
        return _send_for_dispatch(relief_request, relief_request_version, package_version)
    else:
        flash('Invalid action', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=reliefrqst_id))


def _save_draft(relief_request, relief_request_version, package_version):
    """
    Save packaging progress as draft.
    
    Draft packages:
    - Change request status to PART_FILLED (to show in "Being Prepared" tab)
    - Create ReliefPkg with status='P' but verify_by_id=NULL (not submitted for approval)
    - Reserve inventory
    - NO notifications sent
    
    IMPORTANT: Uses atomic transaction to ensure allocations and reservations stay in sync.
    If inventory reservation fails, entire transaction rolls back to prevent phantom allocations.
    Concurrency control is handled via optimistic locking (version_nbr).
    """
    try:
        # OPTIMISTIC LOCKING: Validate relief request version
        _validate_version_nbr("relief request", relief_request_version, relief_request.version_nbr)
        
        # OPTIMISTIC LOCKING: Validate package version if it exists
        existing_pkg = ReliefPkg.query.filter_by(reliefrqst_id=relief_request.reliefrqst_id).first()
        if existing_pkg and package_version:
            _validate_version_nbr("package", package_version, existing_pkg.version_nbr)
        
        # Process and validate allocations (creates ReliefPkgItem records in pending transaction)
        new_allocations = _process_allocations(relief_request, validate_complete=False)
        
        # Change request status to PART_FILLED to show in "Being Prepared" tab
        relief_request.status_code = rr_service.STATUS_PART_FILLED
        relief_request.action_by_id = current_user.user_name
        relief_request.action_dtime = datetime.now()
        relief_request.version_nbr += 1
        
        # Flush to database (still in transaction - not committed yet)
        db.session.flush()
        
        # Attempt inventory reservation BEFORE commit (same transaction)
        # This ensures atomicity: either both allocations and reservations succeed, or both fail
        old_allocations = relief_request._old_allocations if hasattr(relief_request, '_old_allocations') else {}
        success, error_msg = reservation_service.reserve_inventory(
            relief_request.reliefrqst_id,
            new_allocations,
            old_allocations
        )
        
        if not success:
            # Reservation failed - rollback to prevent phantom allocations
            db.session.rollback()
            flash(f'{error_msg}', 'warning')
            flash('Draft not saved due to insufficient inventory. Please adjust allocations or wait for inventory to become available.', 'info')
            return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
        
        # Reservation succeeded - commit both allocations and reservations atomically
        db.session.commit()
        
        flash(f'Draft saved for relief request #{relief_request.reliefrqst_id} with inventory reserved.', 'success')
        
        return redirect(url_for('packaging.pending_fulfillment'))
        
    except OptimisticLockError as e:
        db.session.rollback()
        flash(str(e), 'warning')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving draft: {str(e)}', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))


def _submit_for_approval(relief_request, relief_request_version, package_version):
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
        # OPTIMISTIC LOCKING: Validate relief request version
        _validate_version_nbr("relief request", relief_request_version, relief_request.version_nbr)
        
        # SUBMIT-ONCE GUARD: Prevent multiple LOs from submitting the same relief request
        # Check if package already exists and is ALREADY in PENDING status (submitted for LM approval)
        existing_pkg = ReliefPkg.query.filter_by(reliefrqst_id=relief_request.reliefrqst_id).first()
        
        # OPTIMISTIC LOCKING: Validate package version if it exists
        if existing_pkg and package_version:
            _validate_version_nbr("package", package_version, existing_pkg.version_nbr)
        
        # Store the current package version for optimistic locking check (before processing)
        pkg_version_before = existing_pkg.version_nbr if existing_pkg else None
        
        # A package is considered "already submitted" if it exists and status is PENDING ('P')
        # Status 'P' with a package record means it's either being prepared or already submitted for approval
        # To differentiate, we check if this is a "fresh" submission vs. an update to existing draft
        was_already_pending = existing_pkg and existing_pkg.status_code == rr_service.PKG_STATUS_PENDING
        
        # CRITICAL: If package is already PENDING, only allow the SAME user to update it (not a different LO)
        # This prevents LO #2 from submitting after LO #1 has already submitted
        if was_already_pending and existing_pkg.create_by_id != current_user.user_name:
            flash('This relief request has already been submitted to the Logistics Manager for approval by another user.', 'warning')
            return redirect(url_for('packaging.pending_fulfillment'))
        
        # Process and validate allocations
        new_allocations = _process_allocations(relief_request, validate_complete=False)
        
        # Get the ReliefPkg that was created/updated by _process_allocations
        relief_pkg = ReliefPkg.query.filter_by(reliefrqst_id=relief_request.reliefrqst_id).first()
        if not relief_pkg:
            raise ValueError('Failed to create relief package')
        
        # OPTIMISTIC LOCKING CHECK: Verify package hasn't been modified by another LO in parallel
        # If package existed before and version_nbr has changed, another user modified it
        if pkg_version_before is not None and relief_pkg.version_nbr != pkg_version_before:
            # Package was modified by another user - they may have submitted it
            # Re-check the creator to see if it's a different LO
            if relief_pkg.status_code == rr_service.PKG_STATUS_PENDING and relief_pkg.create_by_id != current_user.user_name:
                flash('This relief request has already been submitted to the Logistics Manager for approval by another user.', 'warning')
                db.session.rollback()
                return redirect(url_for('packaging.pending_fulfillment'))
        
        # Mark package as submitted for approval (status stays 'P' but we're now in "awaiting LM approval" state)
        # Set update_by_id to mark who submitted (LO), but keep verify_by_id NULL until LM actually verifies
        # The "submitted for LM approval" state is indicated by: status='P' + update_by_id set + dispatch_dtime NULL
        relief_pkg.status_code = rr_service.PKG_STATUS_PENDING
        relief_pkg.update_by_id = current_user.user_name
        relief_pkg.update_dtime = datetime.now()
        relief_pkg.version_nbr += 1
        
        # Change request status to PART_FILLED (submitted for approval)
        relief_request.status_code = rr_service.STATUS_PART_FILLED
        relief_request.action_by_id = current_user.user_name
        relief_request.action_dtime = datetime.now()
        relief_request.version_nbr += 1
        
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
        # Only send notifications if this is a NEW submission (not a resubmission)
        if not was_already_pending:
            try:
                from app.services.notification_service import NotificationService
                import logging
                logger = logging.getLogger(__name__)
                
                lm_users = NotificationService.get_active_users_by_role_codes(['LM'])
                logger.info(f'Found {len(lm_users)} Logistics Manager(s) to notify for relief request #{relief_request.reliefrqst_id}')
                
                if lm_users:
                    preparer_name = f"{current_user.first_name} {current_user.last_name}" if current_user.first_name else current_user.email.split('@')[0]
                    notifications = NotificationService.create_package_ready_for_approval_notification(
                        relief_pkg=relief_pkg,
                        recipient_users=lm_users,
                        preparer_name=preparer_name
                    )
                    logger.info(f'Created {len(notifications)} notification(s) for LM approval of relief request #{relief_request.reliefrqst_id}')
                else:
                    logger.warning(f'No Logistics Managers found to notify for relief request #{relief_request.reliefrqst_id}')
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Failed to send LM approval notification: {str(e)}', exc_info=True)
        
        db.session.commit()
        
        flash(f'Relief request #{relief_request.reliefrqst_id} submitted for Logistics Manager approval', 'success')
        return redirect(url_for('packaging.pending_fulfillment'))
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))


def _send_for_dispatch(relief_request, relief_request_version, package_version):
    """
    Send package for dispatch (LM only).
    Workflow: LM fulfills directly → Dispatch to Inventory Clerk (bypasses approval)
    """
    from app.core.rbac import is_logistics_manager
    if not is_logistics_manager():
        flash('Only Logistics Managers can send for dispatch', 'danger')
        return redirect(url_for('packaging.prepare_package', reliefrqst_id=relief_request.reliefrqst_id))
    
    try:
        # OPTIMISTIC LOCKING: Validate relief request version
        _validate_version_nbr("relief request", relief_request_version, relief_request.version_nbr)
        
        # OPTIMISTIC LOCKING: Validate package version if it exists
        existing_pkg = ReliefPkg.query.filter_by(reliefrqst_id=relief_request.reliefrqst_id).first()
        if existing_pkg and package_version:
            _validate_version_nbr("package", package_version, existing_pkg.version_nbr)
        
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
        # Generate tracking number (7-char uppercase from UUID, matching database default)
        tracking_no = str(uuid.uuid4()).replace('-', '').upper()[:7]
        
        # Create a new relief package for tracking allocations
        # NOTE: verify_by_id and received_by_id are NOT set for drafts
        # They will be set when package is submitted for approval or dispatched
        relief_pkg = ReliefPkg(
            agency_id=relief_request.agency_id,
            tracking_no=tracking_no,
            reliefrqst_id=relief_request.reliefrqst_id,
            to_inventory_id=1,  # Placeholder, will be updated on dispatch
            start_date=date.today(),
            status_code='P',  # Preparing
            create_by_id=current_user.user_name,
            create_dtime=datetime.now(),
            update_by_id=current_user.user_name,
            update_dtime=datetime.now(),
            verify_by_id=None,  # NULL for drafts, set when submitted for approval
            received_by_id=None,  # NULL until package is received
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
        
        # Get requested status from form, or use calculated status
        form_status = request.form.get(f'status_{item_id}')
        
        # Check if item has status that allows partial allocation
        # U, D, W: Unavailable items (zero allocation allowed)
        # L, P: Partial fulfillment items (partial allocation allowed)
        partial_allocation_statuses = {'U', 'D', 'W', 'L', 'P'}
        allows_partial = form_status in partial_allocation_statuses if form_status else False
        
        # Validate completeness only if status doesn't explicitly allow partial allocation
        if validate_complete and total_allocated < request_qty and not allows_partial:
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
        
        # Use form_status already retrieved above, or use calculated status
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
            
            # Debug logging
            print(f"DEBUG get_item_batches: item_id={item_id}, remaining_qty={remaining_qty}")
            print(f"DEBUG get_item_batches: allocated_batch_ids={allocated_batch_ids}")
            print(f"DEBUG get_item_batches: limited_batches count={len(limited_batches)}")
            print(f"DEBUG get_item_batches: total_available={total_available}, shortfall={shortfall}")
            
            # Assign priority groups
            batch_groups = BatchAllocationService.assign_priority_groups(limited_batches, item)
            
            # Format batches with priority groups
            result = []
            for batch, priority_group in batch_groups:
                available_qty = batch.usable_qty - batch.reserved_qty
                batch_info = {
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
                }
                result.append(batch_info)
                print(f"DEBUG batch: {batch.batch_id} ({batch.batch_no}) - warehouse={batch_info['warehouse_name']}, expiry={batch_info['expiry_date']}, batch_date={batch_info['batch_date']}, available={available_qty}")
            
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


# ==================== INVENTORY CLERK DISPATCH ROUTES ====================

@packaging_bp.route('/dispatch/awaiting')
@login_required
def awaiting_dispatch():
    """
    Inventory Clerk - Awaiting Dispatch page.
    Shows packages approved by LM and dispatched, filtered by clerk's warehouse(s).
    Only displays items allocated from warehouses the clerk has access to.
    """
    from app.core.rbac import has_role
    
    if not has_role('INVENTORY_CLERK'):
        flash('Access denied. This page is for Inventory Clerks only.', 'danger')
        abort(403)
    
    # Get user's assigned warehouses
    user_warehouse_ids = [w.warehouse_id for w in current_user.warehouses]
    
    if not user_warehouse_ids:
        flash('You have not been assigned to any warehouses. Please contact your administrator.', 'warning')
        return render_template('packaging/awaiting_dispatch.html', 
                             packages=[], 
                             counts={}, 
                             current_filter='awaiting',
                             global_counts={})
    
    # Get filter parameter
    current_filter = request.args.get('filter', 'awaiting')
    
    # Query packages that are dispatched (status='D') but not yet completed
    # Filter to show only packages with items from clerk's warehouse(s)
    from sqlalchemy import func, exists
    
    base_query = db.session.query(ReliefPkg).options(
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefPkg.items)
    ).join(ReliefRqst).filter(
        ReliefPkg.status_code == rr_service.PKG_STATUS_DISPATCHED,
        # Only show packages with items from clerk's warehouses
        exists().where(
            and_(
                ReliefPkgItem.reliefpkg_id == ReliefPkg.reliefpkg_id,
                ReliefPkgItem.fr_inventory_id.in_(user_warehouse_ids)
            )
        )
    )
    
    # Apply filters
    if current_filter == 'awaiting':
        # Not yet handed over (no received_dtime)
        packages = base_query.filter(ReliefPkg.received_dtime == None).order_by(
            ReliefPkg.dispatch_dtime.desc()
        ).all()
    elif current_filter == 'completed':
        # Already handed over (has received_dtime)
        packages = base_query.filter(ReliefPkg.received_dtime != None).order_by(
            ReliefPkg.received_dtime.desc()
        ).all()
    else:  # 'all'
        packages = base_query.order_by(ReliefPkg.dispatch_dtime.desc()).all()
    
    # Calculate counts for filter tabs
    global_counts = {
        'awaiting': base_query.filter(ReliefPkg.received_dtime == None).count(),
        'completed': base_query.filter(ReliefPkg.received_dtime != None).count(),
    }
    global_counts['all'] = global_counts['awaiting'] + global_counts['completed']
    
    # For each package, calculate totals specific to this clerk's warehouses
    package_data = []
    for pkg in packages:
        # Count items and total qty for this clerk's warehouses only
        warehouse_items = [item for item in pkg.items if item.fr_inventory_id in user_warehouse_ids]
        
        package_data.append({
            'package': pkg,
            'relief_request': pkg.relief_request,
            'item_count': len(warehouse_items),
            'total_qty': sum(item.item_qty for item in warehouse_items if item.item_qty),
            'warehouse_items': warehouse_items
        })
    
    counts = global_counts.copy()
    
    return render_template('packaging/awaiting_dispatch.html',
                         packages=package_data,
                         counts=counts,
                         current_filter=current_filter,
                         global_counts=global_counts,
                         user_warehouse_ids=user_warehouse_ids)


@packaging_bp.route('/dispatch/<int:reliefpkg_id>/details')
@login_required
def dispatch_details(reliefpkg_id):
    """
    Dispatch Details page for Inventory Clerk.
    Shows package details for items from clerk's warehouse(s) only.
    Includes print-friendly layout option.
    """
    from app.core.rbac import has_role
    
    if not has_role('INVENTORY_CLERK'):
        flash('Access denied. This page is for Inventory Clerks only.', 'danger')
        abort(403)
    
    # Get user's assigned warehouses
    user_warehouse_ids = [w.warehouse_id for w in current_user.warehouses]
    
    if not user_warehouse_ids:
        flash('You have not been assigned to any warehouses.', 'warning')
        return redirect(url_for('packaging.awaiting_dispatch'))
    
    # Load package with all necessary relationships
    relief_pkg = ReliefPkg.query.options(
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item),
        joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.item),
        joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.batch)
    ).get_or_404(reliefpkg_id)
    
    # Verify package is dispatched
    if relief_pkg.status_code != rr_service.PKG_STATUS_DISPATCHED:
        flash('This package is not in dispatched status.', 'warning')
        return redirect(url_for('packaging.awaiting_dispatch'))
    
    # Filter items to only those from clerk's warehouses
    warehouse_items = [item for item in relief_pkg.items if item.fr_inventory_id in user_warehouse_ids]
    
    if not warehouse_items:
        flash('This package has no items allocated from your assigned warehouses.', 'warning')
        return redirect(url_for('packaging.awaiting_dispatch'))
    
    # Group items by warehouse for display
    from collections import defaultdict
    items_by_warehouse = defaultdict(list)
    for item in warehouse_items:
        items_by_warehouse[item.fr_inventory_id].append(item)
    
    # Get warehouse objects
    warehouses = {w.warehouse_id: w for w in Warehouse.query.filter(
        Warehouse.warehouse_id.in_(user_warehouse_ids)
    ).all()}
    
    # Check if print mode
    print_mode = request.args.get('print', '0') == '1'
    
    return render_template('packaging/dispatch_details.html',
                         relief_pkg=relief_pkg,
                         relief_request=relief_pkg.relief_request,
                         warehouse_items=warehouse_items,
                         items_by_warehouse=items_by_warehouse,
                         warehouses=warehouses,
                         print_mode=print_mode)


@packaging_bp.route('/dispatch/<int:reliefpkg_id>/handover', methods=['POST'])
@login_required
def mark_handover(reliefpkg_id):
    """
    Mark dispatch as handed over to agency.
    Inventory Clerk confirms that items have been physically given to the agency.
    Updates status, triggers notifications to LO/LM.
    """
    from app.core.rbac import has_role
    from app.services.notification_service import NotificationService
    
    if not has_role('INVENTORY_CLERK'):
        flash('Access denied. Only Inventory Clerks can mark handovers.', 'danger')
        abort(403)
    
    # Get user's assigned warehouses
    user_warehouse_ids = [w.warehouse_id for w in current_user.warehouses]
    
    if not user_warehouse_ids:
        flash('You have not been assigned to any warehouses.', 'warning')
        return redirect(url_for('packaging.awaiting_dispatch'))
    
    # Load package
    relief_pkg = ReliefPkg.query.options(
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
        joinedload(ReliefPkg.items)
    ).get_or_404(reliefpkg_id)
    
    # Verify package is dispatched and not already handed over
    if relief_pkg.status_code != rr_service.PKG_STATUS_DISPATCHED:
        flash('This package is not in dispatched status.', 'warning')
        return redirect(url_for('packaging.awaiting_dispatch'))
    
    if relief_pkg.received_dtime:
        flash('This package has already been marked as handed over.', 'info')
        return redirect(url_for('packaging.dispatch_details', reliefpkg_id=reliefpkg_id))
    
    # Verify clerk has items from their warehouse in this package
    warehouse_items = [item for item in relief_pkg.items if item.fr_inventory_id in user_warehouse_ids]
    
    if not warehouse_items:
        flash('This package has no items from your assigned warehouses.', 'warning')
        return redirect(url_for('packaging.awaiting_dispatch'))
    
    try:
        # Mark as received/handed over
        relief_pkg.received_by_id = current_user.user_name
        relief_pkg.received_dtime = datetime.now()
        relief_pkg.update_by_id = current_user.user_name
        relief_pkg.update_dtime = datetime.now()
        
        # Note: Status remains 'D' (Dispatched). We use received_dtime to track handover.
        # Status changes to 'C' (Completed) when agency signs off, if needed.
        
        db.session.commit()
        
        # Send notifications to LO and LM
        try:
            # Get all logistics officers and managers
            lo_users = User.query.filter(User.roles.like('%LOGISTICS_OFFICER%')).all()
            lm_users = User.query.filter(User.roles.like('%LOGISTICS_MANAGER%')).all()
            all_recipients = lo_users + lm_users
            
            if all_recipients:
                # Get warehouse names for notification
                warehouse_names = [w.warehouse_name for w in Warehouse.query.filter(
                    Warehouse.warehouse_id.in_(user_warehouse_ids)
                ).all()]
                warehouse_list = ', '.join(warehouse_names)
                
                agency_name = relief_pkg.relief_request.agency.agency_name if relief_pkg.relief_request.agency else 'Unknown Agency'
                
                for user in all_recipients:
                    notification = Notification(
                        user_id=user.user_id,
                        reliefrqst_id=relief_pkg.reliefrqst_id,
                        title='Package Handed Over to Agency',
                        message=f'Package for {agency_name} (RR-{relief_pkg.reliefrqst_id:06d}) has been handed over from warehouse: {warehouse_list}',
                        type='package_handover',
                        status='unread',
                        link_url=url_for('packaging.dispatch_received_details', reliefpkg_id=relief_pkg.reliefpkg_id, _external=False),
                        is_archived=False
                    )
                    db.session.add(notification)
                
                db.session.commit()
        except Exception as e:
            # Log error but don't fail the handover
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Failed to send handover notification: {str(e)}')
        
        flash(f'Package successfully marked as handed over to {relief_pkg.relief_request.agency.agency_name if relief_pkg.relief_request.agency else "agency"}.', 'success')
        return redirect(url_for('packaging.awaiting_dispatch', filter='completed'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error marking handover: {str(e)}', 'danger')
        return redirect(url_for('packaging.dispatch_details', reliefpkg_id=reliefpkg_id))


# ==================== LO/LM DISPATCH RECEIVED QUEUE ====================

@packaging_bp.route('/dispatch/received')
@login_required
def dispatch_received():
    """
    Logistics Officer/Manager - Dispatch Received queue.
    Shows packages that have been handed over by Inventory Clerks.
    Read-only view for tracking completed dispatches.
    """
    from app.core.rbac import has_role
    
    if not (has_role('LOGISTICS_OFFICER') or has_role('LOGISTICS_MANAGER')):
        flash('Access denied. This page is for Logistics Officers and Managers only.', 'danger')
        abort(403)
    
    # Get filter parameter
    current_filter = request.args.get('filter', 'recent')
    
    # Query packages that have been handed over (have received_dtime)
    base_query = db.session.query(ReliefPkg).options(
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.item),
        joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.batch)
    ).join(ReliefRqst).filter(
        ReliefPkg.status_code == rr_service.PKG_STATUS_DISPATCHED,
        ReliefPkg.received_dtime != None  # Has been handed over
    )
    
    # Apply filters
    if current_filter == 'recent':
        # Last 30 days
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=30)
        packages = base_query.filter(
            ReliefPkg.received_dtime >= cutoff_date
        ).order_by(ReliefPkg.received_dtime.desc()).all()
    else:  # 'all'
        packages = base_query.order_by(ReliefPkg.received_dtime.desc()).all()
    
    # Calculate counts
    from datetime import timedelta
    cutoff_date = datetime.now() - timedelta(days=30)
    global_counts = {
        'recent': base_query.filter(ReliefPkg.received_dtime >= cutoff_date).count(),
        'all': base_query.count()
    }
    
    # Prepare package data with warehouse information
    package_data = []
    for pkg in packages:
        # Get unique warehouses for this package
        warehouse_ids = set(item.fr_inventory_id for item in pkg.items if item.fr_inventory_id)
        warehouses = Warehouse.query.filter(Warehouse.warehouse_id.in_(warehouse_ids)).all() if warehouse_ids else []
        warehouse_names = [w.warehouse_name for w in warehouses]
        
        package_data.append({
            'package': pkg,
            'relief_request': pkg.relief_request,
            'warehouse_names': ', '.join(warehouse_names) if warehouse_names else 'N/A',
            'item_count': len(pkg.items),
            'total_qty': sum(item.item_qty for item in pkg.items if item.item_qty)
        })
    
    counts = global_counts.copy()
    
    return render_template('packaging/dispatch_received.html',
                         packages=package_data,
                         counts=counts,
                         current_filter=current_filter,
                         global_counts=global_counts)


@packaging_bp.route('/dispatch/<int:reliefpkg_id>/received-details')
@login_required
def dispatch_received_details(reliefpkg_id):
    """
    Read-only dispatch details for LO/LM.
    Shows complete package information after handover by Inventory Clerk.
    """
    from app.core.rbac import has_role
    
    if not (has_role('LOGISTICS_OFFICER') or has_role('LOGISTICS_MANAGER')):
        flash('Access denied. This page is for Logistics Officers and Managers only.', 'danger')
        abort(403)
    
    # Load package with all relationships
    relief_pkg = ReliefPkg.query.options(
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.agency),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.eligible_event),
        joinedload(ReliefPkg.relief_request).joinedload(ReliefRqst.items).joinedload(ReliefRqstItem.item),
        joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.item),
        joinedload(ReliefPkg.items).joinedload(ReliefPkgItem.batch)
    ).get_or_404(reliefpkg_id)
    
    # Verify package has been handed over
    if not relief_pkg.received_dtime:
        flash('This package has not been handed over yet.', 'warning')
        return redirect(url_for('packaging.dispatch_received'))
    
    # Group items by warehouse
    from collections import defaultdict
    items_by_warehouse = defaultdict(list)
    for item in relief_pkg.items:
        if item.fr_inventory_id:
            items_by_warehouse[item.fr_inventory_id].append(item)
    
    # Get warehouse objects
    warehouse_ids = set(item.fr_inventory_id for item in relief_pkg.items if item.fr_inventory_id)
    warehouses = {w.warehouse_id: w for w in Warehouse.query.filter(
        Warehouse.warehouse_id.in_(warehouse_ids)
    ).all()} if warehouse_ids else {}
    
    return render_template('packaging/dispatch_received_details.html',
                         relief_pkg=relief_pkg,
                         relief_request=relief_pkg.relief_request,
                         items_by_warehouse=items_by_warehouse,
                         warehouses=warehouses)
