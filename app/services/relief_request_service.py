"""
Relief Request Service Layer
Handles business logic, optimistic locking, and notifications for agency relief requests
"""
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from flask import url_for

from app.db import db
from app.db.models import (
    ReliefRqst, ReliefRqstItem, Item, Event, Agency, User, Notification,
    ReliefPkg, ReliefPkgItem, DBIntake, DBIntakeItem
)
from app.core.exceptions import OptimisticLockError


# Status codes mapping (as per spec)
STATUS_DRAFT = 10
STATUS_SUBMITTED = 20
STATUS_UNDER_REVIEW = 30
STATUS_APPROVED = 40
STATUS_PACKAGE_PREPARED = 60
STATUS_DISPATCHED = 70
STATUS_DELIVERED = 80

URGENCY_HIGH = 'H'
URGENCY_MEDIUM = 'M'
URGENCY_LOW = 'L'


def get_workflow_steps(status_code: int) -> Dict:
    """
    Map status code to workflow step for the dynamic stepper component.
    Returns current step number (1-5) and step metadata.
    """
    if status_code == STATUS_DRAFT:
        return {'current_step': 1, 'step_name': 'Prepare Request', 'status': 'active'}
    elif status_code == STATUS_SUBMITTED:
        return {'current_step': 2, 'step_name': 'Submitted to ODPEM', 'status': 'active'}
    elif status_code in [STATUS_UNDER_REVIEW, STATUS_APPROVED, STATUS_PACKAGE_PREPARED]:
        return {'current_step': 3, 'step_name': 'ODPEM Processing', 'status': 'active'}
    elif status_code == STATUS_DISPATCHED:
        return {'current_step': 4, 'step_name': 'Goods Dispatched', 'status': 'active'}
    elif status_code == STATUS_DELIVERED:
        return {'current_step': 5, 'step_name': 'Goods Received', 'status': 'completed'}
    else:
        return {'current_step': 1, 'step_name': 'Unknown', 'status': 'active'}


def create_draft_request(agency_id: int, urgency_ind: str, eligible_event_id: Optional[int],
                         rqst_notes_text: Optional[str], user_email: str) -> ReliefRqst:
    """
    Create a new draft relief request for an agency.
    
    Args:
        agency_id: ID of the requesting agency
        urgency_ind: H/M/L urgency indicator
        eligible_event_id: Optional associated event ID
        rqst_notes_text: Overall request notes
        user_email: Email of creating user for audit trail
        
    Returns:
        Newly created ReliefRqst instance
    """
    relief_request = ReliefRqst()
    relief_request.agency_id = agency_id
    relief_request.request_date = date.today()
    relief_request.urgency_ind = urgency_ind
    relief_request.eligible_event_id = eligible_event_id
    relief_request.rqst_notes_text = rqst_notes_text
    relief_request.status_code = STATUS_DRAFT
    relief_request.version_nbr = 1
    
    # Audit fields
    relief_request.create_by_id = user_email[:20]
    relief_request.create_dtime = datetime.now()
    
    db.session.add(relief_request)
    db.session.flush()
    
    return relief_request


def add_or_update_request_item(reliefrqst_id: int, item_id: int, request_qty: Decimal,
                                urgency_ind: str, rqst_reason_desc: Optional[str],
                                item_notes_text: Optional[str], user_email: str,
                                current_version: Optional[int] = None) -> ReliefRqstItem:
    """
    Add or update an item on a draft relief request.
    Enforces optimistic locking if updating existing item.
    
    Args:
        reliefrqst_id: Relief request ID
        item_id: Item ID from catalog
        request_qty: Requested quantity
        urgency_ind: Item-level urgency (H/M/L)
        rqst_reason_desc: Justification for requesting this item
        item_notes_text: Additional item notes
        user_email: User performing the action
        current_version: Current version number for optimistic locking (if updating)
        
    Returns:
        ReliefRqstItem instance
        
    Raises:
        OptimisticLockError: If version mismatch on update
    """
    # Check if item already exists
    existing_item = ReliefRqstItem.query.filter_by(
        reliefrqst_id=reliefrqst_id,
        item_id=item_id
    ).first()
    
    if existing_item:
        # Update existing item with optimistic locking
        if current_version is not None and existing_item.version_nbr != current_version:
            raise OptimisticLockError(
                f"Item {item_id} was modified by another user. Please refresh and try again."
            )
        
        existing_item.request_qty = request_qty
        existing_item.urgency_ind = urgency_ind
        existing_item.rqst_reason_desc = rqst_reason_desc
        # Note: item_notes_text is not in the schema, we'll use rqst_reason_desc for notes
        existing_item.version_nbr += 1
        
        return existing_item
    else:
        # Create new item
        request_item = ReliefRqstItem()
        request_item.reliefrqst_id = reliefrqst_id
        request_item.item_id = item_id
        request_item.request_qty = request_qty
        request_item.issue_qty = Decimal('0.00')  # Initially 0, filled by ODPEM
        request_item.urgency_ind = urgency_ind
        request_item.rqst_reason_desc = rqst_reason_desc
        request_item.status_code = 'A'  # Active
        request_item.version_nbr = 1
        
        db.session.add(request_item)
        return request_item


def submit_request(reliefrqst_id: int, current_version: int, user_email: str) -> Tuple[bool, str]:
    """
    Submit a draft relief request to ODPEM for processing.
    Enforces optimistic locking and creates notifications.
    
    Args:
        reliefrqst_id: Relief request ID
        current_version: Current version number for optimistic locking
        user_email: User performing the submission
        
    Returns:
        Tuple of (success: bool, message: str)
        
    Raises:
        OptimisticLockError: If version mismatch
    """
    relief_request = ReliefRqst.query.get_or_404(reliefrqst_id)
    
    # Validate status
    if relief_request.status_code != STATUS_DRAFT:
        return False, f"Only draft requests can be submitted. Current status: {relief_request.status_code}"
    
    # Validate at least one item
    if not relief_request.items or len(relief_request.items) == 0:
        return False, "Cannot submit request without any items"
    
    # Check for items with zero quantity
    items_with_qty = [item for item in relief_request.items if item.request_qty > 0]
    if len(items_with_qty) == 0:
        return False, "Cannot submit request without items with quantity > 0"
    
    # Optimistic locking check
    if relief_request.version_nbr != current_version:
        raise OptimisticLockError(
            "This request was modified by another user. Please refresh and try again."
        )
    
    # Update status
    relief_request.status_code = STATUS_SUBMITTED
    relief_request.action_by_id = user_email[:20]
    relief_request.action_dtime = datetime.now()
    relief_request.version_nbr += 1
    
    db.session.flush()
    
    # Create notifications for ODPEM users (admin users)
    _create_odpem_notifications(relief_request)
    
    # TODO: Send emails to ODPEM distribution list
    
    return True, f"Relief request #{reliefrqst_id} submitted successfully"


def _create_odpem_notifications(relief_request: ReliefRqst) -> None:
    """Create in-app notifications for ODPEM staff about new request submission"""
    # Get all admin users
    admin_users = User.query.filter_by(is_superuser=True, is_active=True).all()
    
    event_name = relief_request.eligible_event.event_name if relief_request.eligible_event else "N/A"
    agency_name = relief_request.agency.agency_name if relief_request.agency else "Unknown"
    
    for admin_user in admin_users:
        notification = Notification(
            user_id=admin_user.id,
            reliefrqst_id=relief_request.reliefrqst_id,
            title='New Relief Request Submitted',
            message=f'Agency {agency_name} submitted relief request #{relief_request.reliefrqst_id} for event: {event_name}',
            type='reliefrqst_submitted',
            status='unread',
            link_url=url_for('requests.view_request', request_id=relief_request.reliefrqst_id, _external=False),
            is_archived=False
        )
        db.session.add(notification)


def create_dispatch_notifications(relief_request: ReliefRqst) -> None:
    """
    Create in-app and email notifications when goods are dispatched for a request.
    Called when status transitions to DISPATCHED (70).
    
    Args:
        relief_request: The ReliefRqst that has been dispatched
    """
    # Get all active users for the requesting agency
    agency_users = User.query.filter_by(
        agency_id=relief_request.agency_id,
        is_active=True
    ).all()
    
    event_name = relief_request.eligible_event.event_name if relief_request.eligible_event else "N/A"
    dispatch_date = datetime.now().strftime('%Y-%m-%d')
    
    for user in agency_users:
        # Create in-app notification
        notification = Notification(
            user_id=user.id,
            reliefrqst_id=relief_request.reliefrqst_id,
            title='Relief Goods Dispatched by ODPEM',
            message=f'ODPEM has dispatched goods for relief request #{relief_request.reliefrqst_id} (Event: {event_name}). Please confirm receipt when delivered.',
            type='reliefrqst_dispatch',
            status='unread',
            link_url=url_for('requests.view_request', request_id=relief_request.reliefrqst_id, _external=False),
            is_archived=False
        )
        db.session.add(notification)
        
        # TODO: Send email notification
        # send_email(
        #     to=user.email,
        #     subject='DRIMS – Goods dispatched for your relief request',
        #     body=f'Dear {user.first_name},\n\n'
        #          f'ODPEM has dispatched goods for your relief request #{relief_request.reliefrqst_id}.\n'
        #          f'Event: {event_name}\n'
        #          f'Dispatch Date: {dispatch_date}\n\n'
        #          f'Please confirm receipt when the goods are delivered.\n\n'
        #          f'View request: {url_for("requests.view_request", request_id=relief_request.reliefrqst_id, _external=True)}'
        # )


def check_and_autoclose_request(reliefrqst_id: int) -> Tuple[bool, str]:
    """
    Check if all allocated goods for a request have been received and auto-close if satisfied.
    Called after each dbintake update.
    
    Logic:
    - For each reliefrqst_item, compare total received usable_qty vs issue_qty
    - Request is fully received when all items are satisfied AND no pending packages
    - Update status to DELIVERED (80) when conditions are met
    
    Args:
        reliefrqst_id: Relief request ID to check
        
    Returns:
        Tuple of (closed: bool, message: str)
    """
    relief_request = ReliefRqst.query.get(reliefrqst_id)
    if not relief_request:
        return False, "Request not found"
    
    # Skip if already closed
    if relief_request.status_code == STATUS_DELIVERED:
        return False, "Request already closed"
    
    # Check for pending packages (status P or D)
    pending_packages = ReliefPkg.query.filter_by(reliefrqst_id=reliefrqst_id).filter(
        ReliefPkg.status_code.in_(['P', 'D'])
    ).count()
    
    if pending_packages > 0:
        return False, f"{pending_packages} package(s) still pending dispatch/receipt"
    
    # Check each item to see if received quantity >= issued quantity
    all_items_satisfied = True
    for req_item in relief_request.items:
        issued_qty = req_item.issue_qty or Decimal('0.00')
        
        # Calculate total received usable quantity for this item across all packages
        received_qty = db.session.query(db.func.sum(DBIntakeItem.usable_qty)).join(
            DBIntake
        ).join(
            ReliefPkg
        ).filter(
            ReliefPkg.reliefrqst_id == reliefrqst_id,
            DBIntakeItem.item_id == req_item.item_id
        ).scalar() or Decimal('0.00')
        
        if received_qty < issued_qty:
            all_items_satisfied = False
            break
    
    if not all_items_satisfied:
        return False, "Not all items have been fully received"
    
    # All conditions met - auto-close the request
    relief_request.status_code = STATUS_DELIVERED
    relief_request.version_nbr += 1
    
    db.session.flush()
    
    # Create notification for agency confirming closure
    _create_closure_notification(relief_request)
    
    return True, f"Relief request #{reliefrqst_id} automatically closed - all goods received"


def _create_closure_notification(relief_request: ReliefRqst) -> None:
    """Create notification for agency when request is auto-closed"""
    agency_users = User.query.filter_by(
        agency_id=relief_request.agency_id,
        is_active=True
    ).all()
    
    for user in agency_users:
        notification = Notification(
            user_id=user.id,
            reliefrqst_id=relief_request.reliefrqst_id,
            title='Relief Request Fully Received and Closed',
            message=f'Relief request #{relief_request.reliefrqst_id} has been fully received and automatically closed. All allocated goods have been confirmed.',
            type='reliefrqst_closed',
            status='unread',
            link_url=url_for('requests.view_request', request_id=relief_request.reliefrqst_id, _external=False),
            is_archived=False
        )
        db.session.add(notification)


def delete_request_item(reliefrqst_id: int, item_id: int) -> Tuple[bool, str]:
    """
    Delete an item from a draft relief request.
    
    Args:
        reliefrqst_id: Relief request ID
        item_id: Item ID to remove
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    # Verify request is in draft status
    relief_request = ReliefRqst.query.get(reliefrqst_id)
    if not relief_request:
        return False, "Request not found"
    
    if relief_request.status_code != STATUS_DRAFT:
        return False, "Can only delete items from draft requests"
    
    # Find and delete the item
    request_item = ReliefRqstItem.query.filter_by(
        reliefrqst_id=reliefrqst_id,
        item_id=item_id
    ).first()
    
    if not request_item:
        return False, "Item not found in request"
    
    db.session.delete(request_item)
    return True, "Item removed successfully"
