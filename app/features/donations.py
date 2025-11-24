"""
Donation Management Routes
Accept and process donations from donors with full item tracking.

Access: LOGISTICS_MANAGER, LOGISTICS_OFFICER only
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.db import db
from app.utils.timezone import now as jamaica_now
from app.db.models import (Donation, DonationItem, DonationDoc, Donor, Event, Custodian, 
                          Item, UnitOfMeasure, Country, Currency, ItemCostDef)
from app.core.audit import add_audit_fields, add_verify_fields
from app.core.decorators import feature_required
import os
from werkzeug.utils import secure_filename
import mimetypes

donations_bp = Blueprint('donations', __name__, url_prefix='/donations')


@donations_bp.route('/debug/items')
@login_required
@feature_required('donation_management')
def debug_items():
    """Debug endpoint to see all items"""
    from app.db.models import ItemCategory
    items = Item.query.filter_by(status_code='A').order_by(Item.item_name).all()
    result = []
    for item in items:
        category = ItemCategory.query.filter_by(category_id=item.category_id).first()
        result.append({
            'item_id': item.item_id,
            'item_name': item.item_name,
            'sku_code': item.sku_code,
            'category_code': category.category_code if category else 'N/A',
            'category_type': category.category_type if category else 'N/A'
        })
    return jsonify({'total': len(result), 'items': result})


def _get_adhoc_event():
    """Get the ADHOC event for default selection"""
    return Event.query.filter(Event.event_name.ilike('%ADHOC%')).first()


def _get_donation_form_data():
    """Get all data needed for donation form dropdowns"""
    donors = Donor.query.order_by(Donor.donor_name).all()
    events = Event.query.filter_by(status_code='A').order_by(Event.event_name).all()
    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
    items = Item.query.filter_by(status_code='A').order_by(Item.item_name).all()
    uoms = UnitOfMeasure.query.filter_by(status_code='A').order_by(UnitOfMeasure.uom_desc).all()
    countries = Country.query.filter_by(status_code='A').order_by(Country.country_name).all()
    currencies = Currency.query.filter_by(status_code='A').order_by(Currency.currency_name).all()
    cost_defs = ItemCostDef.query.filter_by(status_code='A').order_by(ItemCostDef.cost_type, ItemCostDef.cost_name).all()
    adhoc_event = _get_adhoc_event()
    
    items_json = [{'item_id': item.item_id, 'item_name': item.item_name, 'sku_code': item.sku_code, 'default_uom_code': item.default_uom_code} for item in items]
    uoms_json = [{'uom_code': uom.uom_code, 'uom_desc': uom.uom_desc} for uom in uoms]
    countries_json = [{'country_id': c.country_id, 'country_name': c.country_name, 'currency_code': c.currency_code} for c in countries]
    currencies_json = [{'currency_code': cur.currency_code, 'currency_name': cur.currency_name, 'currency_sign': cur.currency_sign} for cur in currencies]
    cost_defs_json = [{'cost_id': cd.cost_id, 'cost_name': cd.cost_name, 'cost_desc': cd.cost_desc, 'cost_type': cd.cost_type} for cd in cost_defs]
    
    return {
        'donors': donors,
        'events': events,
        'custodians': custodians,
        'items': items_json,
        'uoms': uoms_json,
        'countries': countries_json,
        'currencies': currencies_json,
        'cost_defs': cost_defs_json,
        'adhoc_event': adhoc_event,
        'today': date.today().isoformat()
    }


@donations_bp.route('/')
@login_required
@feature_required('donation_management')
def list_donations():
    """List all donations with filter and search capabilities"""
    status_filter = request.args.get('status', 'all')
    donor_filter = request.args.get('donor_id', type=int)
    event_filter = request.args.get('event_id', type=int)
    search_query = request.args.get('search', '').strip()
    
    query = Donation.query
    
    if status_filter != 'all':
        query = query.filter_by(status_code=status_filter.upper())
    
    if donor_filter:
        query = query.filter_by(donor_id=donor_filter)
    
    if event_filter:
        query = query.filter_by(event_id=event_filter)
    
    if search_query:
        query = query.filter(
            db.or_(
                Donation.donation_desc.ilike(f'%{search_query}%'),
                Donation.comments_text.ilike(f'%{search_query}%')
            )
        )
    
    donations = query.order_by(Donation.received_date.desc()).all()
    
    status_counts = {
        'all': Donation.query.count(),
        'E': Donation.query.filter_by(status_code='E').count(),
        'V': Donation.query.filter_by(status_code='V').count(),
        'P': Donation.query.filter_by(status_code='P').count()
    }
    
    donors = Donor.query.order_by(Donor.donor_name).all()
    events = Event.query.filter_by(status_code='A').order_by(Event.event_name).all()
    
    return render_template('donations/list.html', 
                         donations=donations,
                         status_counts=status_counts,
                         current_filter=status_filter,
                         donor_filter=donor_filter,
                         event_filter=event_filter,
                         search_query=search_query,
                         donors=donors,
                         events=events)


@donations_bp.route('/api/item-category/<int:item_id>')
@login_required
@feature_required('donation_management')
def get_item_category(item_id):
    """
    API endpoint to get item category information for dynamic form behavior.
    Returns category_type (GOODS/FUNDS) and category details.
    """
    from app.db.models import ItemCategory
    
    item = Item.query.get_or_404(item_id)
    category = ItemCategory.query.get(item.category_id)
    
    if not category:
        return jsonify({'error': 'Category not found'}), 404
    
    return jsonify({
        'item_id': item.item_id,
        'item_name': item.item_name,
        'sku_code': item.sku_code,
        'category_id': category.category_id,
        'category_code': category.category_code,
        'category_desc': category.category_desc,
        'category_type': category.category_type,
        'default_uom_code': item.default_uom_code
    })


@donations_bp.route('/create', methods=['GET', 'POST'])
@login_required
@feature_required('donation_management')
def create_donation():
    """
    Create new donation with header and items in a single atomic transaction.
    If any validation or save error occurs, rollback entire transaction.
    """
    if request.method == 'POST':
        try:
            donor_id = request.form.get('donor_id')
            event_id = request.form.get('event_id')
            custodian_id = request.form.get('custodian_id')
            donation_desc = request.form.get('donation_desc', '').strip()
            received_date_str = request.form.get('received_date')
            origin_country_id = request.form.get('origin_country_id')
            origin_address1 = request.form.get('origin_address1_text', '').strip()
            origin_address2 = request.form.get('origin_address2_text', '').strip()
            comments_text = request.form.get('comments_text', '').strip()
            
            errors = []
            
            if not donor_id:
                errors.append('Donor is required')
            if not event_id:
                errors.append('Event is required')
            if not custodian_id:
                errors.append('Custodian is required')
            if not donation_desc:
                errors.append('Donation description is required')
            if not received_date_str:
                errors.append('Received date is required')
            
            if received_date_str:
                received_date = datetime.strptime(received_date_str, '%Y-%m-%d').date()
                if received_date > date.today():
                    errors.append('Received date cannot be in the future')
            
            item_data = []
            item_ids_seen = set()
            for key in request.form.keys():
                if key.startswith('item_id_'):
                    item_num = key.split('_')[-1]
                    item_id = request.form.get(f'item_id_{item_num}')
                    donation_type = request.form.get(f'donation_type_{item_num}', 'GOODS').upper()
                    quantity_str = request.form.get(f'quantity_{item_num}')
                    item_cost_str = request.form.get(f'item_cost_{item_num}', '0.00')
                    addon_cost_str = request.form.get(f'addon_cost_{item_num}', '0.00')
                    uom_id = request.form.get(f'uom_id_{item_num}')
                    location_name = request.form.get(f'location_name_{item_num}', 'DONATION RECEIVED').strip()
                    item_comments = request.form.get(f'item_comments_{item_num}', '').strip()
                    
                    if item_id:
                        # Check for duplicate items in the same donation
                        if item_id in item_ids_seen:
                            errors.append(f'Duplicate item detected in row #{item_num}. Each item can only be added once per donation.')
                            continue
                        item_ids_seen.add(item_id)
                        
                        # Validate donation type
                        if donation_type not in ('GOODS', 'FUNDS'):
                            errors.append(f'Invalid donation type for item #{item_num}. Must be GOODS or FUNDS.')
                        
                        # Validate quantity
                        quantity_value = None
                        if not quantity_str:
                            errors.append(f'Quantity is required for item #{item_num}')
                        else:
                            try:
                                quantity_value = Decimal(quantity_str)
                                if quantity_value < 0:
                                    errors.append(f'Quantity must be >= 0 for item #{item_num}')
                            except:
                                errors.append(f'Invalid quantity for item #{item_num}')
                        
                        # Validate item_cost
                        item_cost_value = Decimal('0.00')
                        try:
                            item_cost_value = Decimal(item_cost_str)
                            if item_cost_value < 0:
                                errors.append(f'Item cost must be >= 0 for item #{item_num}')
                        except:
                            errors.append(f'Invalid item cost for item #{item_num}')
                        
                        # Validate addon_cost
                        addon_cost_value = Decimal('0.00')
                        try:
                            addon_cost_value = Decimal(addon_cost_str)
                            if addon_cost_value < 0:
                                errors.append(f'Addon cost must be >= 0 for item #{item_num}')
                        except:
                            errors.append(f'Invalid addon cost for item #{item_num}')
                        
                        # Validate FUNDS-specific rules
                        if donation_type == 'FUNDS':
                            if addon_cost_value != Decimal('0.00'):
                                errors.append(f'Addon cost must be 0.00 for FUNDS items (item #{item_num})')
                        
                        if not uom_id:
                            errors.append(f'UOM is required for item #{item_num}')
                        
                        try:
                            item_data.append({
                                'item_id': int(item_id),
                                'donation_type': donation_type,
                                'quantity': quantity_value,
                                'item_cost': item_cost_value,
                                'addon_cost': addon_cost_value,
                                'uom_code': uom_id,
                                'location_name': location_name,
                                'item_comments': item_comments
                            })
                        except ValueError as ve:
                            errors.append(f'Invalid data for item #{item_num}: {str(ve)}')
            
            if not item_data:
                errors.append('At least one donation item is required')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                form_data = _get_donation_form_data()
                form_data['form_data'] = request.form
                return render_template('donations/create.html', **form_data)
            
            donation = Donation()
            donation.donor_id = int(donor_id)
            donation.event_id = int(event_id)
            donation.custodian_id = int(custodian_id)
            donation.donation_desc = donation_desc.upper()
            donation.received_date = received_date
            donation.origin_country_id = int(origin_country_id) if origin_country_id else None
            donation.origin_address1_text = origin_address1.upper() if origin_address1 else None
            donation.origin_address2_text = origin_address2.upper() if origin_address2 else None
            donation.status_code = 'V'
            donation.comments_text = comments_text.upper() if comments_text else None
            
            current_timestamp = jamaica_now()
            
            add_audit_fields(donation, current_user, is_new=True)
            
            donation.verify_by_id = current_user.user_name
            donation.verify_dtime = current_timestamp
            
            db.session.add(donation)
            db.session.flush()
            
            # Calculate total donation value and validate items before persisting
            from decimal import Decimal
            total_value = Decimal('0.00')
            validated_items = []
            
            for item_info in item_data:
                # Enhanced validation for cost requirements
                donation_type = item_info['donation_type']
                item_cost = item_info['item_cost']
                addon_cost = item_info['addon_cost']
                quantity = item_info['quantity']
                
                # Validate quantity for all types (allow >= 0 to match DB constraint)
                if quantity < 0:
                    errors.append(f"Donation items must have quantity >= 0")
                    continue
                
                if donation_type == 'FUNDS':
                    # FUNDS must have item_cost > 0, addon_cost = 0, and quantity >= 0
                    if item_cost <= 0:
                        errors.append(f"FUNDS donations must have item cost greater than 0.00")
                        continue
                    if addon_cost != 0:
                        errors.append(f"FUNDS donations cannot have addon costs (must be 0.00)")
                        continue
                elif donation_type == 'GOODS':
                    # GOODS should have item_cost >= 0, addon_cost >= 0
                    if item_cost < 0:
                        errors.append(f"GOODS donations cannot have negative item cost")
                        continue
                    if addon_cost < 0:
                        errors.append(f"GOODS donations cannot have negative addon cost")
                        continue
                
                # If item passed validation, add to validated list
                validated_items.append(item_info)
                
                # Add to total value (item_cost + addon_cost) * quantity
                total_value += (Decimal(str(item_cost)) + Decimal(str(addon_cost))) * Decimal(str(quantity))
            
            # Check if there were any validation errors
            if errors:
                db.session.rollback()
                for error in errors:
                    flash(error, 'danger')
                form_data = _get_donation_form_data()
                form_data['form_data'] = request.form
                return render_template('donations/create.html', **form_data)
            
            # All items validated - now persist them
            for item_info in validated_items:
                donation_item = DonationItem()
                donation_item.donation_id = donation.donation_id
                donation_item.item_id = item_info['item_id']
                donation_item.donation_type = item_info['donation_type']
                donation_item.item_qty = item_info['quantity']
                donation_item.item_cost = item_info['item_cost']
                donation_item.addon_cost = item_info['addon_cost']
                donation_item.uom_code = item_info['uom_code']
                donation_item.location_name = item_info['location_name'].upper()
                donation_item.comments_text = item_info['item_comments'].upper() if item_info['item_comments'] else None
                
                add_audit_fields(donation_item, current_user, is_new=True)
                
                donation_item.verify_by_id = current_user.user_name
                donation_item.verify_dtime = current_timestamp
                
                db.session.add(donation_item)
            
            # Set total donated value on donation header
            donation.tot_donated_value = total_value
            
            # Handle document uploads
            document_count = 0
            uploaded_files = request.files.getlist('document_files')
            document_types = request.form.getlist('document_type')
            document_descs = request.form.getlist('document_desc')
            
            for idx, uploaded_file in enumerate(uploaded_files):
                if uploaded_file and uploaded_file.filename and uploaded_file.filename.strip():
                    original_filename = uploaded_file.filename.strip()
                    
                    # Validate file type
                    mime_type = mimetypes.guess_type(original_filename)[0]
                    if mime_type not in ['application/pdf', 'image/jpeg']:
                        errors.append(f'Invalid file type for document {idx + 1}. Only PDF and JPEG files are allowed.')
                        continue
                    
                    # Get document metadata
                    doc_type = document_types[idx] if idx < len(document_types) else 'Other'
                    doc_desc = document_descs[idx] if idx < len(document_descs) else ''
                    
                    if not doc_desc.strip():
                        errors.append(f'Document description is required for document {idx + 1}.')
                        continue
                    
                    # Generate unique safe filename to prevent collisions
                    import uuid
                    safe_base_name = secure_filename(original_filename)
                    file_ext = os.path.splitext(safe_base_name)[1]
                    unique_filename = f"{uuid.uuid4().hex[:8]}_{safe_base_name}"
                    
                    # Create DonationDoc record
                    donation_doc = DonationDoc()
                    donation_doc.donation_id = donation.donation_id
                    donation_doc.document_type = doc_type.upper()
                    donation_doc.document_desc = doc_desc.strip().upper()
                    donation_doc.file_name = unique_filename
                    donation_doc.file_type = mime_type
                    
                    # Calculate file size
                    uploaded_file.seek(0, os.SEEK_END)
                    file_size_bytes = uploaded_file.tell()
                    uploaded_file.seek(0)
                    
                    if file_size_bytes < 1024:
                        donation_doc.file_size = f'{file_size_bytes}B'
                    elif file_size_bytes < 1024 * 1024:
                        donation_doc.file_size = f'{file_size_bytes / 1024:.1f}KB'
                    else:
                        donation_doc.file_size = f'{file_size_bytes / (1024 * 1024):.1f}MB'
                    
                    add_audit_fields(donation_doc, current_user, is_new=True)
                    
                    db.session.add(donation_doc)
                    document_count += 1
            
            db.session.commit()
            
            flash(f'Donation #{donation.donation_id} created successfully with {len(item_data)} item(s) and {document_count} document(s).', 'success')
            return redirect(url_for('donations.view_donation', donation_id=donation.donation_id))
            
        except ValueError as e:
            db.session.rollback()
            flash(f'Validation error: {str(e)}', 'danger')
            form_data = _get_donation_form_data()
            form_data['form_data'] = request.form
            return render_template('donations/create.html', **form_data)
        except IntegrityError as e:
            db.session.rollback()
            error_message = str(e.orig) if hasattr(e, 'orig') else str(e)
            
            # Check if it's a duplicate donation item error
            if ('pk_donation_item' in error_message or 
                'duplicate key' in error_message.lower() or 
                'UNIQUE constraint failed' in error_message):
                flash('Duplicate item detected. Each item can only be added once per donation. Please check your items and try again.', 'danger')
            else:
                flash('Unable to create donation due to a database constraint. Please check your input and try again.', 'danger')
            
            form_data = _get_donation_form_data()
            form_data['form_data'] = request.form
            return render_template('donations/create.html', **form_data)
        except Exception as e:
            db.session.rollback()
            flash(f'Unexpected error: {str(e)}', 'danger')
            form_data = _get_donation_form_data()
            form_data['form_data'] = request.form
            return render_template('donations/create.html', **form_data)
    
    form_data = _get_donation_form_data()
    
    if not form_data['donors']:
        flash('No donors available. Please create a donor first.', 'warning')
        return redirect(url_for('donations.list_donations'))
    
    if not form_data['custodians']:
        flash('No custodians available. Please create a custodian first.', 'warning')
        return redirect(url_for('donations.list_donations'))
    
    if not form_data['items']:
        flash('No items available. Please create items first.', 'warning')
        return redirect(url_for('donations.list_donations'))
    
    if not form_data['uoms']:
        flash('No units of measure available. Please create UOMs first.', 'warning')
        return redirect(url_for('donations.list_donations'))
    
    return render_template('donations/create.html', **form_data)


@donations_bp.route('/<int:donation_id>')
@login_required
@feature_required('donation_management')
def view_donation(donation_id):
    """View donation details including all items"""
    donation = Donation.query.get_or_404(donation_id)
    
    items_with_details = []
    for donation_item in donation.items:
        items_with_details.append({
            'item': donation_item.item,
            'item_qty': donation_item.item_qty,
            'uom': donation_item.uom,
            'location_name': donation_item.location_name,
            'status_code': donation_item.status_code,
            'comments_text': donation_item.comments_text,
            'version_nbr': donation_item.version_nbr
        })
    
    return render_template('donations/view.html', 
                         donation=donation,
                         items=items_with_details)


@donations_bp.route('/<int:donation_id>/edit', methods=['GET', 'POST'])
@login_required
@feature_required('donation_management')
def edit_donation(donation_id):
    """Edit donation header (optimistic locking)"""
    donation = Donation.query.get_or_404(donation_id)
    
    # Prevent editing of verified or processed donations
    if donation.status_code == 'V':
        flash('Cannot edit a verified donation. Donation has been verified and is now read-only.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    # Prevent editing of processed donations (already in warehouse)
    if donation.status_code == 'P':
        flash('Cannot edit a processed donation. It has already been added to warehouse inventory.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    if request.method == 'POST':
        try:
            version_nbr = int(request.form.get('version_nbr', 0))
            
            if version_nbr != donation.version_nbr:
                flash('This donation has been modified by another user. Please reload and try again.', 'danger')
                return redirect(url_for('donations.edit_donation', donation_id=donation_id))
            
            donor_id = request.form.get('donor_id')
            event_id = request.form.get('event_id')
            custodian_id = request.form.get('custodian_id')
            donation_desc = request.form.get('donation_desc', '').strip()
            received_date_str = request.form.get('received_date')
            status_code = request.form.get('status_code')
            comments_text = request.form.get('comments_text', '').strip()
            
            errors = []
            
            if not donor_id:
                errors.append('Donor is required')
            if not event_id:
                errors.append('Event is required')
            if not custodian_id:
                errors.append('Custodian is required')
            if not donation_desc:
                errors.append('Donation description is required')
            if not received_date_str:
                errors.append('Received date is required')
            if not status_code or status_code not in ['E', 'V', 'P']:
                errors.append('Valid status code is required')
            
            if received_date_str:
                received_date = datetime.strptime(received_date_str, '%Y-%m-%d').date()
                if received_date > date.today():
                    errors.append('Received date cannot be in the future')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                donors = Donor.query.order_by(Donor.donor_name).all()
                events = Event.query.filter_by(status_code='A').order_by(Event.event_name).all()
                custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                return render_template('donations/edit.html', 
                                     donation=donation,
                                     donors=donors,
                                     events=events,
                                     custodians=custodians,
                                     today=date.today().isoformat(),
                                     form_data=request.form)
            
            donation.donor_id = int(donor_id)
            donation.event_id = int(event_id)
            donation.custodian_id = int(custodian_id)
            donation.donation_desc = donation_desc.upper()
            
            donation.received_date = received_date
            donation.status_code = status_code
            donation.comments_text = comments_text.upper() if comments_text else None
            
            add_audit_fields(donation, current_user, is_new=False)
            
            # MVP: Any successful update is treated as verified
            # Update verify fields to reflect current user and timestamp
            if status_code == 'V':
                donation.verify_by_id = current_user.user_name
                donation.verify_dtime = jamaica_now()
            
            db.session.commit()
            
            flash(f'Donation #{donation.donation_id} updated successfully', 'success')
            return redirect(url_for('donations.view_donation', donation_id=donation.donation_id))
            
        except StaleDataError:
            db.session.rollback()
            flash('This donation has been modified by another user. Please reload and try again.', 'danger')
            return redirect(url_for('donations.edit_donation', donation_id=donation_id))
        except IntegrityError as e:
            db.session.rollback()
            flash(f'Database error: {str(e)}', 'danger')
            return redirect(url_for('donations.edit_donation', donation_id=donation_id))
    
    donors = Donor.query.order_by(Donor.donor_name).all()
    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
    
    events = Event.query.filter_by(status_code='A').order_by(Event.event_name).all()
    if donation.event not in events:
        events = [donation.event] + events
    
    return render_template('donations/edit.html', 
                         donation=donation,
                         donors=donors,
                         events=events,
                         custodians=custodians,
                         today=date.today().isoformat())


@donations_bp.route('/<int:donation_id>/delete', methods=['POST'])
@login_required
@feature_required('donation_management')
def delete_donation(donation_id):
    """Delete donation (only if no items exist)"""
    donation = Donation.query.get_or_404(donation_id)
    
    # Prevent deleting verified or processed donations
    if donation.status_code == 'V':
        flash('Cannot delete a verified donation. Donation has been verified and is now read-only.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    # Prevent deleting processed donations (already in warehouse)
    if donation.status_code == 'P':
        flash('Cannot delete a processed donation. It has already been added to warehouse inventory.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    if donation.items:
        flash('Cannot delete donation with existing items. Remove all items first.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    try:
        db.session.delete(donation)
        db.session.commit()
        flash(f'Donation #{donation_id} deleted successfully', 'success')
        return redirect(url_for('donations.list_donations'))
    except IntegrityError as e:
        db.session.rollback()
        flash(f'Cannot delete donation: {str(e)}', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))


@donations_bp.route('/<int:donation_id>/items/add', methods=['GET', 'POST'])
@login_required
@feature_required('donation_management')
def add_donation_item(donation_id):
    """Add item to donation"""
    donation = Donation.query.get_or_404(donation_id)
    
    # Prevent adding items to verified or processed donations
    if donation.status_code == 'V':
        flash('Cannot add items to a verified donation. Donation has been verified and items cannot be modified.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    # Prevent adding items to processed donations (already in warehouse)
    if donation.status_code == 'P':
        flash('Cannot add items to a processed donation. It has already been added to warehouse inventory.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    if request.method == 'POST':
        try:
            item_id = request.form.get('item_id')
            item_qty = request.form.get('item_qty')
            uom_code = request.form.get('uom_code')
            location_name = request.form.get('location_name', '').strip()
            comments_text = request.form.get('comments_text', '').strip()
            
            errors = []
            
            if not item_id:
                errors.append('Item is required')
            if not item_qty:
                errors.append('Quantity is required')
            elif Decimal(item_qty) <= 0:
                errors.append('Quantity must be greater than 0')
            if not uom_code:
                errors.append('Unit of measure is required')
            if not location_name:
                errors.append('Location is required')
            
            # Check for duplicate item before attempting database insert
            duplicate_item_id = None
            if item_id:
                existing = DonationItem.query.filter_by(
                    donation_id=donation_id,
                    item_id=int(item_id)
                ).first()
                if existing:
                    errors.append('This item has already been added to the donation. Please edit the existing item instead.')
                    duplicate_item_id = item_id
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                items = Item.query.order_by(Item.item_name).all()
                uoms = UnitOfMeasure.query.order_by(UnitOfMeasure.uom_code).all()
                return render_template('donations/add_item.html',
                                     donation=donation,
                                     items=items,
                                     uoms=uoms,
                                     form_data=request.form,
                                     duplicate_item_id=duplicate_item_id)
            
            donation_item = DonationItem()
            donation_item.donation_id = donation_id
            donation_item.item_id = int(item_id)
            donation_item.item_qty = Decimal(item_qty)
            donation_item.uom_code = uom_code
            donation_item.location_name = location_name.upper()
            donation_item.status_code = 'V'
            donation_item.comments_text = comments_text.upper() if comments_text else None
            
            current_timestamp = jamaica_now()
            
            add_audit_fields(donation_item, current_user, is_new=True)
            
            # MVP: Auto-verify on creation - same user and timestamp as creation
            donation_item.verify_by_id = current_user.user_name
            donation_item.verify_dtime = current_timestamp
            
            db.session.add(donation_item)
            db.session.commit()
            
            flash(f'Item added to donation successfully', 'success')
            return redirect(url_for('donations.view_donation', donation_id=donation_id))
            
        except IntegrityError as e:
            db.session.rollback()
            error_message = str(e.orig) if hasattr(e, 'orig') else str(e)
            
            if ('pk_donation_item' in error_message or 
                'duplicate key' in error_message.lower() or 
                'UNIQUE constraint failed' in error_message):
                flash('This item has already been added to the donation. Please edit the existing item instead.', 'danger')
                items = Item.query.order_by(Item.item_name).all()
                uoms = UnitOfMeasure.query.order_by(UnitOfMeasure.uom_code).all()
                return render_template('donations/add_item.html',
                                     donation=donation,
                                     items=items,
                                     uoms=uoms,
                                     form_data=request.form,
                                     duplicate_item_id=item_id)
            else:
                flash('Unable to add item due to a database constraint. Please check your input and try again.', 'danger')
                items = Item.query.order_by(Item.item_name).all()
                uoms = UnitOfMeasure.query.order_by(UnitOfMeasure.uom_code).all()
                return render_template('donations/add_item.html',
                                     donation=donation,
                                     items=items,
                                     uoms=uoms,
                                     form_data=request.form)
        except Exception as e:
            db.session.rollback()
            flash('An unexpected error occurred. Please try again.', 'danger')
            return redirect(url_for('donations.add_donation_item', donation_id=donation_id))
    
    items = Item.query.order_by(Item.item_name).all()
    uoms = UnitOfMeasure.query.order_by(UnitOfMeasure.uom_code).all()
    
    if not items:
        flash('No items available. Please create items first.', 'warning')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    return render_template('donations/add_item.html',
                         donation=donation,
                         items=items,
                         uoms=uoms)


@donations_bp.route('/<int:donation_id>/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@feature_required('donation_management')
def edit_donation_item(donation_id, item_id):
    """Edit donation item (optimistic locking)"""
    donation = Donation.query.get_or_404(donation_id)
    donation_item = DonationItem.query.get_or_404((donation_id, item_id))
    
    # Prevent editing items from verified or processed donations
    if donation.status_code == 'V':
        flash('Cannot edit items from a verified donation. Donation has been verified and items cannot be modified.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    # Prevent editing of processed donations (already in warehouse)
    if donation.status_code == 'P':
        flash('Cannot edit items from a processed donation. It has already been added to warehouse inventory.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    if request.method == 'POST':
        try:
            version_nbr = int(request.form.get('version_nbr', 0))
            
            if version_nbr != donation_item.version_nbr:
                flash('This item has been modified by another user. Please reload and try again.', 'danger')
                return redirect(url_for('donations.edit_donation_item', 
                                      donation_id=donation_id, 
                                      item_id=item_id))
            
            item_qty = request.form.get('item_qty')
            uom_code = request.form.get('uom_code')
            location_name = request.form.get('location_name', '').strip()
            status_code = request.form.get('status_code')
            comments_text = request.form.get('comments_text', '').strip()
            
            errors = []
            
            if not item_qty:
                errors.append('Quantity is required')
            elif Decimal(item_qty) <= 0:
                errors.append('Quantity must be greater than 0')
            if not uom_code:
                errors.append('Unit of measure is required')
            if not location_name:
                errors.append('Location is required')
            if not status_code or status_code not in ['P', 'V']:
                errors.append('Valid status code is required')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                uoms = UnitOfMeasure.query.order_by(UnitOfMeasure.uom_code).all()
                return render_template('donations/edit_item.html',
                                     donation=donation,
                                     donation_item=donation_item,
                                     uoms=uoms,
                                     form_data=request.form)
            
            donation_item.item_qty = Decimal(item_qty)
            donation_item.uom_code = uom_code
            
            donation_item.location_name = location_name.upper()
            donation_item.status_code = status_code
            donation_item.comments_text = comments_text.upper() if comments_text else None
            
            add_audit_fields(donation_item, current_user, is_new=False)
            
            # MVP: Any successful update is treated as verified
            # Status remains 'V' and verify fields are updated
            if status_code == 'V':
                donation_item.verify_by_id = current_user.user_name
                donation_item.verify_dtime = jamaica_now()
            
            db.session.commit()
            
            flash(f'Donation item updated successfully', 'success')
            return redirect(url_for('donations.view_donation', donation_id=donation_id))
            
        except StaleDataError:
            db.session.rollback()
            flash('This item has been modified by another user. Please reload and try again.', 'danger')
            return redirect(url_for('donations.edit_donation_item', 
                                  donation_id=donation_id, 
                                  item_id=item_id))
        except IntegrityError as e:
            db.session.rollback()
            flash(f'Database error: {str(e)}', 'danger')
            return redirect(url_for('donations.edit_donation_item', 
                                  donation_id=donation_id, 
                                  item_id=item_id))
    
    uoms = UnitOfMeasure.query.order_by(UnitOfMeasure.uom_code).all()
    
    return render_template('donations/edit_item.html',
                         donation=donation,
                         donation_item=donation_item,
                         uoms=uoms)


@donations_bp.route('/<int:donation_id>/items/<int:item_id>/delete', methods=['POST'])
@login_required
@feature_required('donation_management')
def delete_donation_item(donation_id, item_id):
    """Delete donation item"""
    donation = Donation.query.get_or_404(donation_id)
    donation_item = DonationItem.query.get_or_404((donation_id, item_id))
    
    # Prevent deleting items from verified or processed donations
    if donation.status_code == 'V':
        flash('Cannot delete items from a verified donation. Donation has been verified and items cannot be modified.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    # Prevent deleting items from processed donations (already in warehouse)
    if donation.status_code == 'P':
        flash('Cannot delete items from a processed donation. It has already been added to warehouse inventory.', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    
    try:
        db.session.delete(donation_item)
        db.session.commit()
        flash(f'Donation item removed successfully', 'success')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))
    except IntegrityError as e:
        db.session.rollback()
        flash(f'Cannot delete item: {str(e)}', 'danger')
        return redirect(url_for('donations.view_donation', donation_id=donation_id))


# DISABLED: Separate verification workflow removed for MVP
# Donations are now auto-verified during acceptance (create_donation)
# @donations_bp.route('/<int:donation_id>/verify', methods=['POST'])
# @login_required
# @feature_required('donation_management')
# def verify_donation(donation_id):
#     """
#     DEPRECATED: Verification now happens automatically during donation acceptance.
#     This endpoint is disabled for MVP. All donations are verified on creation.
#     """
#     flash('Donations are automatically verified when accepted. No separate verification needed.', 'info')
#     return redirect(url_for('donations.view_donation', donation_id=donation_id))
