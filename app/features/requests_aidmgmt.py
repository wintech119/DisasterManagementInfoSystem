"""
Agency Relief Request Management (AIDMGMT Workflow)
Allows agency users to prepare and submit relief requests for disaster response.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy.exc import SQLAlchemyError

from app.db import db
from app.db.models import ReliefRqst, ReliefRqstItem, Agency, Item, Event, UnitOfMeasure
from app.core.rbac import agency_user_required, is_admin
from app.core.exceptions import OptimisticLockError
from app.services import relief_request_service as rr_service

requests_bp = Blueprint('requests', __name__, url_prefix='/relief-requests')


@requests_bp.route('/')
@login_required
@agency_user_required
def list_requests():
    """
    List all relief requests for the current user's agency.
    Agency users only see their own agency's requests.
    """
    status_filter = request.args.get('status', 'all')
    
    # Filter by current user's agency
    query = ReliefRqst.query.filter_by(agency_id=current_user.agency_id)
    
    # Apply status filter
    if status_filter == 'draft':
        query = query.filter_by(status_code=rr_service.STATUS_DRAFT)
    elif status_filter == 'submitted':
        query = query.filter_by(status_code=rr_service.STATUS_SUBMITTED)
    elif status_filter == 'processing':
        query = query.filter(ReliefRqst.status_code.in_([
            rr_service.STATUS_AWAITING_APPROVAL,
            rr_service.STATUS_PART_FILLED
        ]))
    elif status_filter == 'dispatched':
        query = query.filter_by(status_code=rr_service.STATUS_CLOSED)
    elif status_filter == 'completed':
        query = query.filter_by(status_code=rr_service.STATUS_FILLED)
    
    requests_list = query.order_by(ReliefRqst.request_date.desc()).all()
    
    # Add workflow metadata for each request
    for req in requests_list:
        req.workflow_step = rr_service.get_workflow_steps(req.status_code)
    
    return render_template('requests/list.html',
                         requests=requests_list,
                         status_filter=status_filter,
                         STATUS_DRAFT=rr_service.STATUS_DRAFT,
                         STATUS_SUBMITTED=rr_service.STATUS_SUBMITTED,
                         STATUS_CLOSED=rr_service.STATUS_CLOSED,
                         STATUS_FILLED=rr_service.STATUS_FILLED)


@requests_bp.route('/create', methods=['GET', 'POST'])
@login_required
@agency_user_required
def create_request():
    """Create new draft relief request for current user's agency"""
    if request.method == 'POST':
        try:
            urgency_ind = request.form.get('urgency_ind', 'M')
            eligible_event_id = request.form.get('eligible_event_id')
            eligible_event_id = int(eligible_event_id) if eligible_event_id else None
            rqst_notes_text = request.form.get('rqst_notes_text', '').strip()
            
            # Validate urgency
            if urgency_ind not in ['H', 'M', 'L']:
                flash('Invalid urgency level', 'danger')
                return redirect(url_for('requests.create_request'))
            
            # Create draft request
            relief_request = rr_service.create_draft_request(
                agency_id=current_user.agency_id,
                urgency_ind=urgency_ind,
                eligible_event_id=eligible_event_id,
                rqst_notes_text=rqst_notes_text,
                user_email=current_user.email
            )
            
            db.session.commit()
            
            flash(f'Draft relief request #{relief_request.reliefrqst_id} created successfully. Add items to continue.', 'success')
            return redirect(url_for('requests.edit_items', request_id=relief_request.reliefrqst_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating request: {str(e)}', 'danger')
            return redirect(url_for('requests.create_request'))
    
    # GET request - show form
    events = Event.query.filter_by(status_code='A').order_by(Event.start_date.desc()).all()
    
    return render_template('requests/create.html',
                         events=events,
                         today=date.today().isoformat())


@requests_bp.route('/<int:request_id>')
@login_required
@agency_user_required
def view_request(request_id):
    """View relief request details"""
    relief_request = ReliefRqst.query.get_or_404(request_id)
    
    # Verify request belongs to current agency
    if relief_request.agency_id != current_user.agency_id:
        flash('You do not have permission to view this request.', 'danger')
        abort(403)
    
    # Add workflow metadata
    relief_request.workflow_step = rr_service.get_workflow_steps(relief_request.status_code)
    
    return render_template('requests/view.html',
                         request=relief_request,
                         STATUS_DRAFT=rr_service.STATUS_DRAFT,
                         STATUS_SUBMITTED=rr_service.STATUS_SUBMITTED,
                         STATUS_CLOSED=rr_service.STATUS_CLOSED,
                         STATUS_FILLED=rr_service.STATUS_FILLED)


@requests_bp.route('/<int:request_id>/edit', methods=['GET', 'POST'])
@login_required
@agency_user_required
def edit_request(request_id):
    """Edit relief request header (only for drafts)"""
    relief_request = ReliefRqst.query.get_or_404(request_id)
    
    # Verify ownership
    if relief_request.agency_id != current_user.agency_id:
        flash('You do not have permission to edit this request.', 'danger')
        abort(403)
    
    # Can only edit drafts
    if relief_request.status_code != rr_service.STATUS_DRAFT:
        flash('Only draft requests can be edited.', 'warning')
        return redirect(url_for('requests.view_request', request_id=request_id))
    
    if request.method == 'POST':
        try:
            current_version = int(request.form.get('version_nbr'))
            
            # Optimistic locking check
            if relief_request.version_nbr != current_version:
                raise OptimisticLockError('This request was modified by another user. Please refresh.')
            
            # Update fields
            relief_request.urgency_ind = request.form.get('urgency_ind', 'M')
            eligible_event_id = request.form.get('eligible_event_id')
            relief_request.eligible_event_id = int(eligible_event_id) if eligible_event_id else None
            relief_request.rqst_notes_text = request.form.get('rqst_notes_text', '').strip()
            relief_request.version_nbr += 1
            
            db.session.commit()
            
            flash('Request updated successfully', 'success')
            return redirect(url_for('requests.view_request', request_id=request_id))
            
        except OptimisticLockError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return redirect(url_for('requests.edit_request', request_id=request_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating request: {str(e)}', 'danger')
    
    events = Event.query.filter_by(status_code='A').order_by(Event.start_date.desc()).all()
    
    return render_template('requests/edit.html',
                         request=relief_request,
                         events=events)


@requests_bp.route('/<int:request_id>/items', methods=['GET'])
@login_required
@agency_user_required
def get_items(request_id):
    """API endpoint: Get all items for a request"""
    relief_request = ReliefRqst.query.get_or_404(request_id)
    
    # Verify ownership
    if relief_request.agency_id != current_user.agency_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    items_data = []
    for req_item in relief_request.items:
        items_data.append({
            'item_id': req_item.item_id,
            'item_name': req_item.item.item_name,
            'sku_code': req_item.item.sku_code,
            'category': req_item.item.category.category_desc if req_item.item.category else '',
            'request_qty': float(req_item.request_qty),
            'issue_qty': float(req_item.issue_qty),
            'urgency_ind': req_item.urgency_ind,
            'rqst_reason_desc': req_item.rqst_reason_desc or '',
            'status_code': req_item.status_code,
            'version_nbr': req_item.version_nbr
        })
    
    return jsonify({'items': items_data})


@requests_bp.route('/<int:request_id>/items/edit', methods=['GET', 'POST'])
@login_required
@agency_user_required
def edit_items(request_id):
    """Add/edit items on a draft relief request"""
    relief_request = ReliefRqst.query.get_or_404(request_id)
    
    # Verify ownership
    if relief_request.agency_id != current_user.agency_id:
        flash('You do not have permission to edit this request.', 'danger')
        abort(403)
    
    # Can only edit items on drafts
    if relief_request.status_code != rr_service.STATUS_DRAFT:
        flash('Items can only be edited on draft requests.', 'warning')
        return redirect(url_for('requests.view_request', request_id=request_id))
    
    if request.method == 'POST':
        try:
            item_id = int(request.form.get('item_id'))
            request_qty = Decimal(request.form.get('request_qty', '0'))
            urgency_ind = request.form.get('urgency_ind', 'M')
            rqst_reason_desc = request.form.get('rqst_reason_desc', '').strip()
            
            # Validate item is active
            item = Item.query.get_or_404(item_id)
            if item.status_code != 'A':
                flash('Cannot add inactive items to request', 'danger')
                return redirect(url_for('requests.edit_items', request_id=request_id))
            
            if request_qty <= 0:
                flash('Quantity must be greater than zero', 'danger')
                return redirect(url_for('requests.edit_items', request_id=request_id))
            
            # Add or update item
            rr_service.add_or_update_request_item(
                reliefrqst_id=request_id,
                item_id=item_id,
                request_qty=request_qty,
                urgency_ind=urgency_ind,
                rqst_reason_desc=rqst_reason_desc,
                item_notes_text=None,  # Not used
                user_email=current_user.email
            )
            
            db.session.commit()
            
            flash(f'Item "{item.item_name}" added successfully', 'success')
            return redirect(url_for('requests.edit_items', request_id=request_id))
            
        except OptimisticLockError as e:
            db.session.rollback()
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding item: {str(e)}', 'danger')
    
    # GET request - show items and add form
    active_items = Item.query.filter_by(status_code='A').order_by(Item.item_name).all()
    
    return render_template('requests/edit_items.html',
                         request=relief_request,
                         active_items=active_items)


@requests_bp.route('/<int:request_id>/items/<int:item_id>/delete', methods=['POST'])
@login_required
@agency_user_required
def delete_item(request_id, item_id):
    """Delete an item from a draft request"""
    relief_request = ReliefRqst.query.get_or_404(request_id)
    
    # Verify ownership
    if relief_request.agency_id != current_user.agency_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        success, message = rr_service.delete_request_item(request_id, item_id)
        
        if success:
            db.session.commit()
            flash(message, 'success')
        else:
            flash(message, 'warning')
        
        return redirect(url_for('requests.edit_items', request_id=request_id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting item: {str(e)}', 'danger')
        return redirect(url_for('requests.edit_items', request_id=request_id))


@requests_bp.route('/<int:request_id>/submit', methods=['POST'])
@login_required
@agency_user_required
def submit_request(request_id):
    """Submit a draft relief request to ODPEM for processing"""
    relief_request = ReliefRqst.query.get_or_404(request_id)
    
    # Verify ownership
    if relief_request.agency_id != current_user.agency_id:
        flash('You do not have permission to submit this request.', 'danger')
        abort(403)
    
    try:
        current_version = int(request.form.get('version_nbr'))
        
        success, message = rr_service.submit_request(
            reliefrqst_id=request_id,
            current_version=current_version,
            user_email=current_user.email
        )
        
        if success:
            db.session.commit()
            flash(message, 'success')
        else:
            flash(message, 'warning')
        
        return redirect(url_for('requests.view_request', request_id=request_id))
        
    except OptimisticLockError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('requests.view_request', request_id=request_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting request: {str(e)}', 'danger')
        return redirect(url_for('requests.view_request', request_id=request_id))
