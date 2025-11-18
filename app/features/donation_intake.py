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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from decimal import Decimal
from datetime import datetime, date

from app.db import db
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
    
    # Base query
    query = db.session.query(DonationIntake).join(Donation).join(Warehouse)
    
    # Apply filters
    if filter_type == 'recent':
        # Last 30 days
        thirty_days_ago = date.today() - timedelta(days=30)
        query = query.filter(DonationIntake.intake_date >= thirty_days_ago)
    
    # Apply search
    if search_query:
        query = query.filter(
            db.or_(
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
    verified_donations = Donation.query.filter_by(status_code='V').order_by(
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
    
    if request.method == 'POST':
        try:
            # Validate and process intake
            result = _process_intake_submission(donation, warehouse, existing_intake)
            
            if result['success']:
                flash(result['message'], 'success')
                return redirect(url_for('donation_intake.list_intakes'))
            else:
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
                         existing_intake=existing_intake,
                         today=date.today().isoformat())


def _process_intake_submission(donation, warehouse, existing_intake):
    """
    Process intake form submission.
    Validates all data and creates/updates intake records in a single transaction.
    
    Returns dict with 'success', 'message', and 'errors' keys.
    """
    errors = []
    
    # Extract form data
    intake_date_str = request.form.get('intake_date')
    comments_text = request.form.get('comments_text', '').strip()
    
    # Validate intake date
    if not intake_date_str:
        errors.append('Intake date is required')
    else:
        intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()
        if intake_date > date.today():
            errors.append('Intake date cannot be in the future')
    
    # Validate comments length
    if len(comments_text) > 255:
        errors.append('Comments must be 255 characters or less')
    
    # Collect and validate intake items
    intake_items = []
    donation_items = DonationItem.query.filter_by(donation_id=donation.donation_id).all()
    
    # Track total quantities per item
    item_totals = {}
    
    for key in request.form.keys():
        if key.startswith('batch_no_'):
            item_id = int(key.split('_')[-1])
            
            batch_no = request.form.get(f'batch_no_{item_id}', '').strip().upper()
            batch_date_str = request.form.get(f'batch_date_{item_id}')
            expiry_date_str = request.form.get(f'expiry_date_{item_id}')
            uom_code = request.form.get(f'uom_code_{item_id}')
            avg_unit_value_str = request.form.get(f'avg_unit_value_{item_id}')
            usable_qty_str = request.form.get(f'usable_qty_{item_id}', '0')
            defective_qty_str = request.form.get(f'defective_qty_{item_id}', '0')
            expired_qty_str = request.form.get(f'expired_qty_{item_id}', '0')
            item_comments = request.form.get(f'item_comments_{item_id}', '').strip()
            
            # Get item details
            item = Item.query.get(item_id)
            if not item:
                errors.append(f'Invalid item ID: {item_id}')
                continue
            
            # Validate batch number
            if item.is_batched_flag and not batch_no:
                errors.append(f'{item.item_name} requires a batch number')
                continue
            
            if not batch_no:
                batch_no = f'NOBATCH-{item_id}'
            
            # Validate batch date
            if not batch_date_str:
                errors.append(f'Batch date is required for {item.item_name}')
                continue
            
            batch_date = datetime.strptime(batch_date_str, '%Y-%m-%d').date()
            if batch_date > date.today():
                errors.append(f'Batch date cannot be in the future for {item.item_name}')
                continue
            
            # Validate expiry date
            expiry_date = None
            if expiry_date_str:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                if item.can_expire_flag and expiry_date < date.today():
                    errors.append(f'Expiry date has already passed for {item.item_name}')
                    continue
            elif item.can_expire_flag:
                errors.append(f'Expiry date is required for {item.item_name}')
                continue
            
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
                
                total_qty = usable_qty + defective_qty + expired_qty
                if total_qty == 0:
                    errors.append(f'Total quantity cannot be zero for {item.item_name}')
                    continue
                
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
    
    # Validate total quantities match donation quantities
    for donation_item in donation_items:
        expected_qty = donation_item.item_qty
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
        current_timestamp = datetime.now()
        
        # Create or update dnintake header
        if existing_intake:
            intake = existing_intake
            add_audit_fields(intake, current_user, is_new=False)
        else:
            intake = DonationIntake()
            intake.donation_id = donation.donation_id
            intake.inventory_id = warehouse.warehouse_id
            intake.status_code = 'V'
            add_audit_fields(intake, current_user, is_new=True)
            intake.verify_by_id = current_user.user_name
            intake.verify_dtime = current_timestamp
            db.session.add(intake)
        
        intake.intake_date = intake_date
        intake.comments_text = comments_text.upper() if comments_text else None
        
        # Delete existing intake items if updating
        if existing_intake:
            DonationIntakeItem.query.filter_by(
                donation_id=donation.donation_id,
                inventory_id=warehouse.warehouse_id
            ).delete()
        
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
            
            # Create itembatch record
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
            
            # Update or create inventory record
            inventory = Inventory.query.get((warehouse.warehouse_id, item_data['item_id']))
            if inventory:
                inventory.usable_qty = (inventory.usable_qty or Decimal('0')) + item_data['usable_qty']
                inventory.defective_qty = (inventory.defective_qty or Decimal('0')) + item_data['defective_qty']
                inventory.expired_qty = (inventory.expired_qty or Decimal('0')) + item_data['expired_qty']
                add_audit_fields(inventory, current_user, is_new=False)
            else:
                inventory = Inventory()
                inventory.inventory_id = warehouse.warehouse_id
                inventory.item_id = item_data['item_id']
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


from datetime import timedelta
