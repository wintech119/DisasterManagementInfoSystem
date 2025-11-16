from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime
from app.db.models import db, Donor, Donation
from app.core.audit import add_audit_fields
from app.core.phone_utils import validate_phone_format, get_phone_validation_error

donors_bp = Blueprint('donors', __name__)

@donors_bp.route('/')
@login_required
def list_donors():
    donors = Donor.query.order_by(Donor.donor_name).all()
    return render_template('donors/index.html', donors=donors)

@donors_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        donor_type = request.form.get('donor_type')
        donor_name = request.form.get('donor_name', '').strip().upper()
        org_type_desc = request.form.get('org_type_desc', '').strip() or None
        address1_text = request.form.get('address1_text', '').strip()
        address2_text = request.form.get('address2_text', '').strip() or None
        country_id = int(request.form.get('country_id', 388))
        phone_no = request.form.get('phone_no', '').strip()
        email_text = request.form.get('email_text', '').strip().lower() or None
        
        if not donor_name or not donor_type or not address1_text or not phone_no:
            flash('Please fill in all required fields.', 'danger')
            countries = db.session.execute(db.text("SELECT country_id, country_name FROM country ORDER BY country_name")).fetchall()
            return render_template('donors/create.html', countries=countries)
        
        # Validate phone number format
        if not validate_phone_format(phone_no):
            flash(get_phone_validation_error('Phone number'), 'danger')
            countries = db.session.execute(db.text("SELECT country_id, country_name FROM country ORDER BY country_name")).fetchall()
            return render_template('donors/create.html', countries=countries)
        
        if Donor.query.filter_by(donor_name=donor_name).first():
            flash(f'A donor with the name {donor_name} already exists.', 'danger')
            countries = db.session.execute(db.text("SELECT country_id, country_name FROM country ORDER BY country_name")).fetchall()
            return render_template('donors/create.html', countries=countries)
        
        new_donor = Donor(
            donor_type=donor_type,
            donor_name=donor_name,
            org_type_desc=org_type_desc,
            address1_text=address1_text,
            address2_text=address2_text,
            country_id=country_id,
            phone_no=phone_no,
            email_text=email_text
        )
        
        add_audit_fields(new_donor, current_user)
        
        db.session.add(new_donor)
        db.session.commit()
        
        flash(f'Donor {donor_name} created successfully.', 'success')
        return redirect(url_for('donors.view', donor_id=new_donor.donor_id))
    
    countries = db.session.execute(db.text("SELECT country_id, country_name FROM country ORDER BY country_name")).fetchall()
    return render_template('donors/create.html', countries=countries)

@donors_bp.route('/<int:donor_id>')
@login_required
def view(donor_id):
    donor = Donor.query.get_or_404(donor_id)
    donations = Donation.query.filter_by(donor_id=donor_id).order_by(Donation.received_date.desc()).all()
    return render_template('donors/view.html', donor=donor, donations=donations)

@donors_bp.route('/<int:donor_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(donor_id):
    donor = Donor.query.get_or_404(donor_id)
    
    if request.method == 'POST':
        phone_no = request.form.get('phone_no', '').strip()
        
        # Validate phone number format
        if phone_no and not validate_phone_format(phone_no):
            flash(get_phone_validation_error('Phone number'), 'danger')
            countries = db.session.execute(db.text("SELECT country_id, country_name FROM country ORDER BY country_name")).fetchall()
            return render_template('donors/edit.html', donor=donor, countries=countries)
        
        donor.donor_type = request.form.get('donor_type')
        donor.org_type_desc = request.form.get('org_type_desc', '').strip() or None
        donor.address1_text = request.form.get('address1_text', '').strip()
        donor.address2_text = request.form.get('address2_text', '').strip() or None
        donor.country_id = int(request.form.get('country_id', 388))
        donor.phone_no = phone_no
        donor.email_text = request.form.get('email_text', '').strip().lower() or None
        
        add_audit_fields(donor, current_user, is_new=False)
        
        db.session.commit()
        
        flash(f'Donor {donor.donor_name} updated successfully.', 'success')
        return redirect(url_for('donors.view', donor_id=donor.donor_id))
    
    countries = db.session.execute(db.text("SELECT country_id, country_name FROM country ORDER BY country_name")).fetchall()
    return render_template('donors/edit.html', donor=donor, countries=countries)
