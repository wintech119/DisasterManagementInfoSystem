"""
Batch Management Blueprint
Handles CRUD operations for item batches with batch-level inventory tracking.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import joinedload
from decimal import Decimal
from datetime import date, datetime

from app.db import db
from app.db.models import ItemBatch, Item, Inventory, Warehouse, UnitOfMeasure
from app.core.decorators import feature_required

batches_bp = Blueprint('batches', __name__, url_prefix='/batches')


@batches_bp.route('/')
@login_required
@feature_required('MASTER_DATA_MGMT')
def list_batches():
    """
    Display list of all batches with filtering and search capabilities.
    Restricted to CUSTODIAN role.
    """
    # Get filter parameters
    status_filter = request.args.get('status', 'active')
    warehouse_filter = request.args.get('warehouse', '', type=int)
    item_filter = request.args.get('item', '', type=int)
    search_query = request.args.get('search', '').strip()
    
    # Base query with eager loading
    query = ItemBatch.query.options(
        joinedload(ItemBatch.item),
        joinedload(ItemBatch.inventory).joinedload(Inventory.warehouse),
        joinedload(ItemBatch.uom)
    )
    
    # Apply status filter
    if status_filter == 'active':
        query = query.filter(ItemBatch.status_code == 'A')
    elif status_filter == 'unavailable':
        query = query.filter(ItemBatch.status_code == 'U')
    elif status_filter == 'expired':
        query = query.filter(
            ItemBatch.status_code == 'A',
            ItemBatch.expiry_date < date.today()
        )
    elif status_filter == 'expiring_soon':
        # Expires within 30 days
        from datetime import timedelta
        soon_date = date.today() + timedelta(days=30)
        query = query.filter(
            ItemBatch.status_code == 'A',
            ItemBatch.expiry_date.isnot(None),
            ItemBatch.expiry_date <= soon_date,
            ItemBatch.expiry_date >= date.today()
        )
    
    # Apply warehouse filter
    if warehouse_filter:
        query = query.filter(ItemBatch.inventory_id == warehouse_filter)
    
    # Apply item filter
    if item_filter:
        query = query.filter(ItemBatch.item_id == item_filter)
    
    # Apply search filter
    if search_query:
        search_pattern = f'%{search_query.upper()}%'
        query = query.join(Item).filter(
            or_(
                ItemBatch.batch_no.ilike(search_pattern),
                Item.item_name.ilike(search_pattern),
                Item.item_code.ilike(search_pattern)
            )
        )
    
    # Order by most recent first
    batches = query.order_by(ItemBatch.batch_date.desc()).all()
    
    # Calculate summary metrics
    total_batches = len(batches)
    active_batches = sum(1 for b in batches if b.status_code == 'A')
    
    # Calculate expired and expiring soon counts
    today = date.today()
    expired_count = sum(1 for b in batches if b.expiry_date and b.expiry_date < today and b.status_code == 'A')
    
    from datetime import timedelta
    soon_date = today + timedelta(days=30)
    expiring_soon_count = sum(1 for b in batches if b.expiry_date and today <= b.expiry_date <= soon_date and b.status_code == 'A')
    
    # Calculate total quantities
    total_usable = sum(b.usable_qty for b in batches if b.status_code == 'A')
    total_reserved = sum(b.reserved_qty for b in batches if b.status_code == 'A')
    total_available = total_usable - total_reserved
    
    # Get warehouses and items for filters
    warehouses = Warehouse.query.filter_by(status_code='A').order_by(Warehouse.warehouse_name).all()
    items = Item.query.filter_by(is_batched_flag=True, status_code='A').order_by(Item.item_name).all()
    
    return render_template(
        'batches/list.html',
        batches=batches,
        status_filter=status_filter,
        warehouse_filter=warehouse_filter,
        item_filter=item_filter,
        search_query=search_query,
        total_batches=total_batches,
        active_batches=active_batches,
        expired_count=expired_count,
        expiring_soon_count=expiring_soon_count,
        total_usable=total_usable,
        total_reserved=total_reserved,
        total_available=total_available,
        warehouses=warehouses,
        items=items
    )


@batches_bp.route('/create', methods=['GET', 'POST'])
@login_required
@feature_required('MASTER_DATA_MGMT')
def create_batch():
    """Create a new batch. Restricted to CUSTODIAN role."""
    if request.method == 'POST':
        try:
            # Get form data
            inventory_id = request.form.get('inventory_id', type=int)
            item_id = request.form.get('item_id', type=int)
            batch_no = request.form.get('batch_no', '').strip().upper()
            batch_date_str = request.form.get('batch_date', '').strip()
            expiry_date_str = request.form.get('expiry_date', '').strip()
            usable_qty = Decimal(request.form.get('usable_qty', '0'))
            uom_code = request.form.get('uom_code', '').strip().upper()
            size_spec = request.form.get('size_spec', '').strip()
            avg_unit_value = Decimal(request.form.get('avg_unit_value', '0'))
            comments = request.form.get('comments', '').strip()
            
            # Validation
            errors = []
            
            if not inventory_id:
                errors.append('Warehouse is required')
            
            if not item_id:
                errors.append('Item is required')
            else:
                # Verify item is batched
                item = Item.query.get(item_id)
                if not item:
                    errors.append('Invalid item selected')
                elif not item.is_batched_flag:
                    errors.append('Selected item does not support batch tracking')
            
            if not batch_no:
                errors.append('Batch number is required')
            elif len(batch_no) > 30:
                errors.append('Batch number must be 30 characters or less')
            
            # Check for duplicate batch number
            if batch_no and item_id and inventory_id:
                existing = ItemBatch.query.filter_by(
                    batch_no=batch_no,
                    item_id=item_id,
                    inventory_id=inventory_id
                ).first()
                if existing:
                    errors.append(f'Batch number "{batch_no}" already exists for this item at this warehouse')
            
            if not batch_date_str:
                errors.append('Batch date is required')
            else:
                try:
                    batch_date = datetime.strptime(batch_date_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append('Invalid batch date format')
                    batch_date = None
            
            # Parse expiry date (optional)
            expiry_date = None
            if expiry_date_str:
                try:
                    expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                    # Validate expiry date is after batch date
                    if batch_date and expiry_date <= batch_date:
                        errors.append('Expiry date must be after batch date')
                except ValueError:
                    errors.append('Invalid expiry date format')
            
            if usable_qty <= 0:
                errors.append('Usable quantity must be greater than zero')
            
            if not uom_code:
                errors.append('Unit of measure is required')
            else:
                # Verify UOM exists
                uom = UnitOfMeasure.query.get(uom_code)
                if not uom:
                    errors.append('Invalid unit of measure')
            
            if avg_unit_value < 0:
                errors.append('Average unit value cannot be negative')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                # Re-render form with submitted data
                warehouses = Warehouse.query.filter_by(status_code='A').order_by(Warehouse.warehouse_name).all()
                items = Item.query.filter_by(is_batched_flag=True, status_code='A').order_by(Item.item_name).all()
                uoms = UnitOfMeasure.query.filter_by(status_code='A').order_by(UnitOfMeasure.uom_code).all()
                
                return render_template(
                    'batches/create.html',
                    warehouses=warehouses,
                    items=items,
                    uoms=uoms,
                    form_data=request.form
                )
            
            # Create new batch
            new_batch = ItemBatch(
                inventory_id=inventory_id,
                item_id=item_id,
                batch_no=batch_no,
                batch_date=batch_date,
                expiry_date=expiry_date,
                usable_qty=usable_qty,
                reserved_qty=Decimal('0'),
                defective_qty=Decimal('0'),
                expired_qty=Decimal('0'),
                uom_code=uom_code,
                size_spec=size_spec,
                avg_unit_value=avg_unit_value,
                verified_flag=False,
                status_code='A',
                comments=comments,
                create_by_id=current_user.user_name,
                create_dtime=datetime.now(),
                update_by_id=current_user.user_name,
                update_dtime=datetime.now(),
                version_nbr=1
            )
            
            db.session.add(new_batch)
            db.session.commit()
            
            flash(f'Batch "{batch_no}" created successfully', 'success')
            return redirect(url_for('batches.view_batch', batch_id=new_batch.batch_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating batch: {str(e)}', 'danger')
    
    # GET request - show form
    warehouses = Warehouse.query.filter_by(status_code='A').order_by(Warehouse.warehouse_name).all()
    items = Item.query.filter_by(is_batched_flag=True, status_code='A').order_by(Item.item_name).all()
    uoms = UnitOfMeasure.query.filter_by(status_code='A').order_by(UnitOfMeasure.uom_code).all()
    
    return render_template(
        'batches/create.html',
        warehouses=warehouses,
        items=items,
        uoms=uoms,
        form_data={}
    )


@batches_bp.route('/<int:batch_id>')
@login_required
@feature_required('MASTER_DATA_MGMT')
def view_batch(batch_id):
    """View detailed information about a specific batch."""
    batch = ItemBatch.query.options(
        joinedload(ItemBatch.item),
        joinedload(ItemBatch.inventory).joinedload(Inventory.warehouse),
        joinedload(ItemBatch.uom)
    ).get_or_404(batch_id)
    
    # Calculate derived values
    available_qty = batch.usable_qty - batch.reserved_qty
    is_expired = batch.expiry_date and batch.expiry_date < date.today()
    
    # Calculate days until expiry
    days_until_expiry = None
    if batch.expiry_date and not is_expired:
        days_until_expiry = (batch.expiry_date - date.today()).days
    
    return render_template(
        'batches/view.html',
        batch=batch,
        available_qty=available_qty,
        is_expired=is_expired,
        days_until_expiry=days_until_expiry
    )


@batches_bp.route('/<int:batch_id>/edit', methods=['GET', 'POST'])
@login_required
@feature_required('MASTER_DATA_MGMT')
def edit_batch(batch_id):
    """Edit an existing batch. Restricted to CUSTODIAN role."""
    batch = ItemBatch.query.get_or_404(batch_id)
    
    if request.method == 'POST':
        try:
            # Get version number for optimistic locking
            version_nbr = request.form.get('version_nbr', type=int)
            
            if version_nbr != batch.version_nbr:
                flash('This batch was modified by another user. Please review the changes and try again.', 'warning')
                return redirect(url_for('batches.view_batch', batch_id=batch_id))
            
            # Get form data (only editable fields)
            expiry_date_str = request.form.get('expiry_date', '').strip()
            usable_qty = Decimal(request.form.get('usable_qty', '0'))
            reserved_qty = Decimal(request.form.get('reserved_qty', '0'))
            defective_qty = Decimal(request.form.get('defective_qty', '0'))
            expired_qty = Decimal(request.form.get('expired_qty', '0'))
            size_spec = request.form.get('size_spec', '').strip()
            avg_unit_value = Decimal(request.form.get('avg_unit_value', '0'))
            verified_flag = request.form.get('verified_flag') == 'on'
            status_code = request.form.get('status_code', '').strip().upper()
            comments = request.form.get('comments', '').strip()
            
            # Validation
            errors = []
            
            # Parse expiry date
            expiry_date = None
            if expiry_date_str:
                try:
                    expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                    if expiry_date <= batch.batch_date:
                        errors.append('Expiry date must be after batch date')
                except ValueError:
                    errors.append('Invalid expiry date format')
            
            if usable_qty < 0:
                errors.append('Usable quantity cannot be negative')
            
            if reserved_qty < 0:
                errors.append('Reserved quantity cannot be negative')
            
            if reserved_qty > usable_qty:
                errors.append('Reserved quantity cannot exceed usable quantity')
            
            if defective_qty < 0:
                errors.append('Defective quantity cannot be negative')
            
            if expired_qty < 0:
                errors.append('Expired quantity cannot be negative')
            
            if avg_unit_value < 0:
                errors.append('Average unit value cannot be negative')
            
            if status_code not in ['A', 'U']:
                errors.append('Invalid status code')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('batches/edit.html', batch=batch, form_data=request.form)
            
            # Update batch
            batch.expiry_date = expiry_date
            batch.usable_qty = usable_qty
            batch.reserved_qty = reserved_qty
            batch.defective_qty = defective_qty
            batch.expired_qty = expired_qty
            batch.size_spec = size_spec
            batch.avg_unit_value = avg_unit_value
            batch.verified_flag = verified_flag
            batch.status_code = status_code
            batch.comments = comments
            batch.update_by_id = current_user.user_name
            batch.update_dtime = datetime.now()
            
            db.session.commit()
            
            flash(f'Batch "{batch.batch_no}" updated successfully', 'success')
            return redirect(url_for('batches.view_batch', batch_id=batch_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating batch: {str(e)}', 'danger')
    
    # GET request - show form
    return render_template('batches/edit.html', batch=batch, form_data={})


@batches_bp.route('/api/by-item/<int:item_id>')
@login_required
def api_batches_by_item(item_id):
    """API endpoint to get batches for a specific item (for dropdowns)."""
    warehouse_id = request.args.get('warehouse_id', type=int)
    
    query = ItemBatch.query.filter_by(
        item_id=item_id,
        status_code='A'
    ).options(
        joinedload(ItemBatch.inventory).joinedload(Inventory.warehouse)
    )
    
    if warehouse_id:
        query = query.filter_by(inventory_id=warehouse_id)
    
    batches = query.order_by(ItemBatch.batch_date.desc()).all()
    
    return jsonify([{
        'batch_id': b.batch_id,
        'batch_no': b.batch_no,
        'warehouse_name': b.inventory.warehouse.warehouse_name,
        'batch_date': b.batch_date.isoformat() if b.batch_date else None,
        'expiry_date': b.expiry_date.isoformat() if b.expiry_date else None,
        'available_qty': float(b.usable_qty - b.reserved_qty),
        'uom_code': b.uom_code
    } for b in batches])
