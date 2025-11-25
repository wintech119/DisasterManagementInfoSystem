"""
Donation Intake Blueprint

Handles the intake of verified donations into warehouse inventory.
Only accessible to Logistics Officers and Logistics Managers.

Key Features:
- Select verified donations (status='V')
- Choose target warehouse/inventory
- Create dnintake headers and items with batch tracking
- Auto-create itembatch records
- Update inventory totals
- Mark donations as Processed

Author: DRIMS Development Team
Date: 2025-11-18
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from decimal import Decimal
from datetime import datetime, date, timedelta

from app.db import db
from app.utils.timezone import now as jamaica_now
from app.db.models import (
    Donation, DonationItem, DonationIntake, DonationIntakeItem,
    Item, ItemBatch, Warehouse, Inventory, UnitOfMeasure
)
from app.core.decorators import feature_required
from app.core.audit import add_audit_fields


donation_intake_bp = Blueprint('donation_intake', __name__, url_prefix='/donation-intake')


@donation_intake_bp.route('/')
@login_required
@feature_required('donation_intake_management')
def list_intakes():
    """
    List all donation intakes.
    Shows intake history with filters.
    """
    # Get filter parameters
    filter_type = request.args.get('filter', 'all')
    search_query = request.args.get('search', '').strip()
    
    # Base query with explicit joins
    query = db.session.query(DonationIntake).join(
        Donation, DonationIntake.donation_id == Donation.donation_id
    ).join(
        Warehouse, DonationIntake.inventory_id == Warehouse.warehouse_id
    )
    
    # Apply filters
    if filter_type == 'recent':
        # Last 30 days
        thirty_days_ago = date.today() - timedelta(days=30)
        query = query.filter(DonationIntake.intake_date >= thirty_days_ago)
    
    # Apply search
    if search_query:
        query = query.filter(
            or_(
                Donation.donation_desc.ilike(f'%{search_query}%'),
                Warehouse.warehouse_name.ilike(f'%{search_query}%')
            )
        )
    
    intakes = query.order_by(DonationIntake.intake_date.desc()).all()
    
    # Calculate counts
    all_count = db.session.query(DonationIntake).count()
    recent_count = db.session.query(DonationIntake).filter(
        DonationIntake.intake_date >= date.today() - timedelta(days=30)
    ).count()
    
    counts = {
        'all': all_count,
        'recent': recent_count
    }
    
    return render_template('donation_intake/list.html',
                         intakes=intakes,
                         current_filter=filter_type,
                         search_query=search_query,
                         counts=counts)


@donation_intake_bp.route('/create', methods=['GET', 'POST'])
@login_required
@feature_required('donation_intake_management')
def create_intake():
    """
    Step 1: Select donation and warehouse for intake.
    Shows list of verified donations and available warehouses.
    """
    if request.method == 'POST':
        donation_id = request.form.get('donation_id')
        inventory_id = request.form.get('inventory_id')
        
        if not donation_id or not inventory_id:
            flash('Please select both a donation and a warehouse', 'danger')
            return redirect(url_for('donation_intake.create_intake'))
        
        # Redirect to intake form with selected donation and warehouse
        return redirect(url_for('donation_intake.intake_form',
                              donation_id=donation_id,
                              inventory_id=inventory_id))
    
    # Get verified donations (status='V') that haven't been processed
    # Eager load items to get correct count
    from sqlalchemy.orm import joinedload
    
    verified_donations = Donation.query.filter_by(status_code='V').options(
        joinedload(Donation.items)
    ).order_by(
        Donation.received_date.desc()
    ).all()
    
    # Get active warehouses
    warehouses = Warehouse.query.filter_by(status_code='A').order_by(
        Warehouse.warehouse_name
    ).all()
    
    return render_template('donation_intake/create.html',
                         verified_donations=verified_donations,
                         warehouses=warehouses)


@donation_intake_bp.route('/intake/<int:donation_id>/<int:inventory_id>', methods=['GET', 'POST'])
@login_required
@feature_required('donation_intake_management')
def intake_form(donation_id, inventory_id):
    """
    Step 2: Complete intake form with donation items and batch details.
    Creates dnintake header and items, creates itembatch records,
    updates inventory, and marks donation as Processed.
    """
    donation = Donation.query.get_or_404(donation_id)
    warehouse = Warehouse.query.get_or_404(inventory_id)
    
    # Check if donation is verified
    if donation.status_code != 'V':
        flash('Only verified donations can be intaken', 'danger')
        return redirect(url_for('donation_intake.list_intakes'))
    
    # Check if intake already exists for this donation/warehouse combination
    existing_intake = DonationIntake.query.get((donation_id, inventory_id))
    
    # For MVP: Prevent duplicate processing of same donation/warehouse
    if existing_intake:
        flash(f'Intake already exists for Donation #{donation_id} at {warehouse.warehouse_name}', 'warning')
        return redirect(url_for('donation_intake.list_intakes'))
    
    if request.method == 'POST':
        try:
            # Validate and process intake (existing_intake=None due to check above)
            result = _process_intake_submission(donation, warehouse)
            
            if result['success']:
                flash(result['message'], 'success')
                return redirect(url_for('donation_intake.list_intakes'))
            else:
                # Ensure rollback on validation/business logic errors
                db.session.rollback()
                for error in result['errors']:
                    flash(error, 'danger')
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing intake: {str(e)}', 'danger')
    
    # Get donation items
    donation_items = DonationItem.query.filter_by(
        donation_id=donation_id
    ).join(Item).all()
    
    # Get UOMs for dropdown
    uoms = UnitOfMeasure.query.filter_by(status_code='A').order_by(
        UnitOfMeasure.uom_desc
    ).all()
    
    return render_template('donation_intake/intake_form.html',
                         donation=donation,
                         warehouse=warehouse,
                         donation_items=donation_items,
                         uoms=uoms,
                         today=date.today().isoformat())


def _process_intake_submission(donation, warehouse):
    """
    Process intake form submission.
    Validates all data and creates intake records in a single transaction.
    
    MVP: Does not support updates to existing intakes (prevented by route check).
    
    Returns dict with 'success', 'message', and 'errors' keys.
    """
    errors = []
    
    # Extract form data
    intake_date_str = request.form.get('intake_date')
    comments_text = request.form.get('comments_text', '').strip()
    
    # Initialize intake_date to None to avoid unbound variable
    intake_date = None
    
    # Validate intake date
    if not intake_date_str:
        errors.append('Intake date is required')
    else:
        try:
            intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()
            if intake_date > date.today():
                errors.append('Intake date cannot be in the future')
        except ValueError:
            errors.append('Invalid intake date format')
    
    # Validate comments length
    if len(comments_text) > 255:
        errors.append('Comments must be 255 characters or less')
    
    # Collect and validate intake items
    # Loop over authoritative donation items from database to prevent bypass
    intake_items = []
    donation_items = DonationItem.query.filter_by(donation_id=donation.donation_id).all()
    
    # Track total quantities per item
    item_totals = {}
    
    # Validate ALL items BEFORE creating any objects
    for donation_item in donation_items:
        item_id = donation_item.item_id
        
        # Ensure form data exists for this item
        batch_no_key = f'batch_no_{item_id}'
        if batch_no_key not in request.form:
            errors.append(f'{donation_item.item.item_name}: Missing intake data in form submission')
            continue
            
        # Get form data for this item (read raw values once)
        batch_no_raw = request.form.get(batch_no_key, '').strip().upper()
        batch_date_str = request.form.get(f'batch_date_{item_id}', '').strip()
        expiry_date_str = request.form.get(f'expiry_date_{item_id}')
        uom_code = request.form.get(f'uom_code_{item_id}')
        avg_unit_value_str = request.form.get(f'avg_unit_value_{item_id}')
        usable_qty_str = request.form.get(f'usable_qty_{item_id}', '0')
        defective_qty_str = request.form.get(f'defective_qty_{item_id}', '0')
        expired_qty_str = request.form.get(f'expired_qty_{item_id}', '0')
        item_comments = request.form.get(f'item_comments_{item_id}', '').strip()
        
        # Get item details from donation_item (already loaded from DB)
        item = donation_item.item
        
        # Initialize normalized values before validation (single-pass normalization pattern)
        normalized_batch_no = None
        normalized_batch_date = None
        
        # Paired validation for batch_no and batch_date
        # CRITICAL: Database allows batch_no to be NULL (nullable column)
        # Valid states: (1) Both empty, (2) Both filled, (3) One filled/one empty = ERROR
        # Enforce pairing: if one field has a value, the other must also have a value
        
        if batch_no_raw and not batch_date_str:
            # ERROR: Batch No provided but Batch Date missing
            errors.append(f'{item.item_name}: Please enter a Batch Date when a Batch No is provided')
            continue
        elif not batch_no_raw and batch_date_str:
            # ERROR: Batch Date provided but Batch No missing
            errors.append(f'{item.item_name}: Please enter a Batch No when a Batch Date is provided')
            continue
        
        # At this point: either both are filled, or both are empty
        if batch_no_raw and batch_date_str:
            # Both filled - validate and parse batch date
            try:
                normalized_batch_date = datetime.strptime(batch_date_str, '%Y-%m-%d').date()
                if normalized_batch_date > date.today():
                    errors.append(f'Batch date cannot be in the future for {item.item_name}')
                    continue
            except ValueError:
                errors.append(f'Invalid batch date format for {item.item_name}')
                continue
            # Set normalized values after validation passes
            normalized_batch_no = batch_no_raw
        else:
            # Both empty - save as NULL (no NOBATCH placeholder)
            normalized_batch_no = None
            normalized_batch_date = None
        
        # Use normalized values for batch_no and batch_date going forward
        batch_no = normalized_batch_no
        batch_date = normalized_batch_date
        
        # Validate expiry date (required for items that can expire)
        expiry_date = None
        if item.can_expire_flag:
            # For items that can expire, expiry date is required
            if not expiry_date_str:
                errors.append(f'{item.item_name}: Expiry Date is required for items that can expire.')
                continue
            try:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                if expiry_date < date.today():
                    errors.append(f'Expiry date has already passed for {item.item_name}')
                    continue
            except ValueError:
                errors.append(f'Invalid expiry date format for {item.item_name}')
                continue
        # For items that cannot expire, ignore any submitted expiry date
        # (expiry_date remains None)
        
        # Validate UOM
        if not uom_code:
            errors.append(f'UOM is required for {item.item_name}')
            continue
        
        # Validate quantities
        try:
            usable_qty = Decimal(usable_qty_str) if usable_qty_str else Decimal('0')
            defective_qty = Decimal(defective_qty_str) if defective_qty_str else Decimal('0')
            expired_qty = Decimal(expired_qty_str) if expired_qty_str else Decimal('0')
            
            if usable_qty < 0 or defective_qty < 0 or expired_qty < 0:
                errors.append(f'Quantities cannot be negative for {item.item_name}')
                continue
            
            # Reject if usable quantity is zero (entire donation is defective/expired)
            if usable_qty == 0:
                errors.append(f'{item.item_name}: Usable quantity cannot be zero. At least some portion of the donation must be usable.')
                continue
            
            # Calculate total quantity for tracking
            total_qty = usable_qty + defective_qty + expired_qty
            
        except:
            errors.append(f'Invalid quantities for {item.item_name}')
            continue
        
        # Validate unit value
        try:
            avg_unit_value = Decimal(avg_unit_value_str) if avg_unit_value_str else Decimal('0')
            if avg_unit_value <= 0:
                errors.append(f'Unit value must be greater than 0 for {item.item_name}')
                continue
        except:
            errors.append(f'Invalid unit value for {item.item_name}')
            continue
        
        # Track totals
        if item_id not in item_totals:
            item_totals[item_id] = Decimal('0')
        item_totals[item_id] += total_qty
        
        intake_items.append({
            'item_id': item_id,
            'item': item,
            'batch_no': batch_no,
            'batch_date': batch_date,
            'expiry_date': expiry_date,
            'uom_code': uom_code,
            'avg_unit_value': avg_unit_value,
            'usable_qty': usable_qty,
            'defective_qty': defective_qty,
            'expired_qty': expired_qty,
            'comments_text': item_comments.upper() if item_comments else None
        })
    
    # Check for duplicate batch numbers within this submission (only for items with batch tracking)
    seen_batches = set()
    for intake_item in intake_items:
        # Skip items without batch numbers (batch_no = None means no batch tracking)
        if intake_item['batch_no'] is None:
            continue
            
        batch_key = (intake_item['item_id'], intake_item['batch_no'])
        if batch_key in seen_batches:
            errors.append(
                f'{intake_item["item"].item_name}: Duplicate batch number "{intake_item["batch_no"]}" in this submission. '
                f'Each item can only have one batch per intake.'
            )
        seen_batches.add(batch_key)
    
    # Check if batch numbers already exist in database for items with batch tracking
    # Filter out items without batch numbers (batch_no = None)
    batched_items = [item for item in intake_items if item['batch_no'] is not None]
    
    if batched_items:
        from sqlalchemy import tuple_
        batch_pairs = [(item['item_id'], item['batch_no']) for item in batched_items]
        
        existing_batches = ItemBatch.query.filter(
            tuple_(ItemBatch.item_id, ItemBatch.batch_no).in_(batch_pairs)
        ).all()
        
        # Map existing batches to item names for user-friendly error messages
        if existing_batches:
            # Create lookup of item_id to item_name from batched_items
            item_name_map = {item['item_id']: item['item'].item_name for item in batched_items}
            
            for existing_batch in existing_batches:
                item_name = item_name_map.get(existing_batch.item_id, f'Item ID {existing_batch.item_id}')
                errors.append(
                    f'{item_name}: This batch number "{existing_batch.batch_no}" already exists for this item. '
                    f'Please enter a unique batch number.'
                )
    
    # Validate total quantities match donation quantities (from database, not form)
    # Fetch authoritative donation quantities from database to prevent bypass
    db_donation_items = {di.item_id: di.item_qty for di in donation_items}
    
    for donation_item in donation_items:
        expected_qty = db_donation_items[donation_item.item_id]  # Authoritative qty from DB
        actual_qty = item_totals.get(donation_item.item_id, Decimal('0'))
        
        if actual_qty != expected_qty:
            item_name = donation_item.item.item_name
            errors.append(
                f'{item_name}: Intake quantity ({actual_qty}) must equal donation quantity ({expected_qty})'
            )
    
    # Check if all donation items are accounted for
    for donation_item in donation_items:
        if donation_item.item_id not in item_totals:
            errors.append(f'{donation_item.item.item_name} must have at least one intake entry')
    
    if errors:
        return {'success': False, 'errors': errors, 'message': None}
    
    # Process the intake
    try:
        current_timestamp = jamaica_now()
        
        # Create dnintake header (existing_intake check prevents duplicates)
        intake = DonationIntake()
        intake.donation_id = donation.donation_id
        intake.inventory_id = warehouse.warehouse_id
        intake.intake_date = intake_date
        intake.comments_text = comments_text.upper() if comments_text else None
        intake.status_code = 'V'
        add_audit_fields(intake, current_user, is_new=True)
        intake.verify_by_id = current_user.user_name
        intake.verify_dtime = current_timestamp
        db.session.add(intake)
        
        # Create intake items and batches
        for item_data in intake_items:
            # Create intake item
            intake_item = DonationIntakeItem()
            intake_item.donation_id = donation.donation_id
            intake_item.inventory_id = warehouse.warehouse_id
            intake_item.item_id = item_data['item_id']
            intake_item.batch_no = item_data['batch_no']
            intake_item.batch_date = item_data['batch_date']
            intake_item.expiry_date = item_data['expiry_date']
            intake_item.uom_code = item_data['uom_code']
            intake_item.avg_unit_value = item_data['avg_unit_value']
            intake_item.usable_qty = item_data['usable_qty']
            intake_item.defective_qty = item_data['defective_qty']
            intake_item.expired_qty = item_data['expired_qty']
            intake_item.status_code = 'V'
            intake_item.comments_text = item_data['comments_text']
            
            add_audit_fields(intake_item, current_user, is_new=True)
            
            db.session.add(intake_item)
            
            # Create or update itembatch record
            # CRITICAL: Database has UNIQUE constraint on (inventory_id, batch_no, item_id)
            # When batch_no is NULL, use update_or_create to prevent IntegrityError
            if item_data['batch_no'] is None:
                # NULL batch_no: Find existing batch or create new one
                existing_batch = ItemBatch.query.filter_by(
                    inventory_id=warehouse.warehouse_id,
                    item_id=item_data['item_id'],
                    batch_no=None
                ).first()
                
                if existing_batch:
                    # Update existing batch by adding quantities
                    existing_batch.usable_qty += item_data['usable_qty']
                    existing_batch.defective_qty += item_data['defective_qty']
                    existing_batch.expired_qty += item_data['expired_qty']
                    add_audit_fields(existing_batch, current_user, is_new=False)
                    item_batch = existing_batch
                else:
                    # Create new batch with NULL batch_no
                    item_batch = ItemBatch()
                    item_batch.inventory_id = warehouse.warehouse_id
                    item_batch.item_id = item_data['item_id']
                    item_batch.batch_no = None
                    item_batch.batch_date = None
                    item_batch.expiry_date = item_data['expiry_date']
                    item_batch.uom_code = item_data['uom_code']
                    item_batch.avg_unit_value = item_data['avg_unit_value']
                    item_batch.usable_qty = item_data['usable_qty']
                    item_batch.defective_qty = item_data['defective_qty']
                    item_batch.expired_qty = item_data['expired_qty']
                    item_batch.reserved_qty = Decimal('0')
                    item_batch.status_code = 'A'
                    item_batch.comments_text = item_data['comments_text']
                    add_audit_fields(item_batch, current_user, is_new=True)
                    db.session.add(item_batch)
            else:
                # Regular batch with batch_no: Always create new batch (duplicates already validated)
                item_batch = ItemBatch()
                item_batch.inventory_id = warehouse.warehouse_id
                item_batch.item_id = item_data['item_id']
                item_batch.batch_no = item_data['batch_no']
                item_batch.batch_date = item_data['batch_date']
                item_batch.expiry_date = item_data['expiry_date']
                item_batch.uom_code = item_data['uom_code']
                item_batch.avg_unit_value = item_data['avg_unit_value']
                item_batch.usable_qty = item_data['usable_qty']
                item_batch.defective_qty = item_data['defective_qty']
                item_batch.expired_qty = item_data['expired_qty']
                item_batch.reserved_qty = Decimal('0')
                item_batch.status_code = 'A'
                item_batch.comments_text = item_data['comments_text']
                add_audit_fields(item_batch, current_user, is_new=True)
                db.session.add(item_batch)
            
            # Update or create inventory record with optimistic locking
            inventory = Inventory.query.filter_by(
                inventory_id=warehouse.warehouse_id,
                item_id=item_data['item_id']
            ).with_for_update().first()
            
            if inventory:
                # Use optimistic locking to prevent race conditions
                inventory.usable_qty = (inventory.usable_qty or Decimal('0')) + item_data['usable_qty']
                inventory.defective_qty = (inventory.defective_qty or Decimal('0')) + item_data['defective_qty']
                inventory.expired_qty = (inventory.expired_qty or Decimal('0')) + item_data['expired_qty']
                add_audit_fields(inventory, current_user, is_new=False)
            else:
                inventory = Inventory()
                inventory.inventory_id = warehouse.warehouse_id
                inventory.item_id = item_data['item_id']
                inventory.uom_code = item_data['uom_code']
                inventory.usable_qty = item_data['usable_qty']
                inventory.defective_qty = item_data['defective_qty']
                inventory.expired_qty = item_data['expired_qty']
                inventory.reserved_qty = Decimal('0')
                inventory.status_code = 'A'
                add_audit_fields(inventory, current_user, is_new=True)
                db.session.add(inventory)
        
        # Update donation status to Processed
        donation.status_code = 'P'
        add_audit_fields(donation, current_user, is_new=False)
        
        db.session.commit()
        
        message = f'Donation #{donation.donation_id} successfully intaken to {warehouse.warehouse_name}'
        return {'success': True, 'message': message, 'errors': []}
        
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'errors': [f'Database error: {str(e)}'], 'message': None}


