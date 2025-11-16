from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.db.models import db, User, Role, UserRole, UserWarehouse, Warehouse, Agency, Custodian
from app.core.rbac import role_required

user_admin_bp = Blueprint('user_admin', __name__)

@user_admin_bp.route('/')
@login_required
@role_required('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')
def index():
    users = User.query.order_by(User.create_dtime.desc()).all()
    
    total_users = len(users)
    active_users = sum(1 for u in users if u.is_active)
    inactive_users = sum(1 for u in users if not u.is_active)
    locked_users = sum(1 for u in users if u.is_locked)
    
    mfa_enabled_users = sum(1 for u in users if u.mfa_enabled)
    mfa_percentage = round((mfa_enabled_users / total_users * 100) if total_users > 0 else 0, 1)
    
    admin_role_codes = ['SYSTEM_ADMINISTRATOR', 'SYS_ADMIN']
    admin_users = sum(1 for u in users if any(r.code in admin_role_codes for r in u.roles))
    
    metrics = {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'locked_users': locked_users,
        'mfa_enabled': mfa_enabled_users,
        'mfa_percentage': mfa_percentage,
        'admin_users': admin_users
    }
    
    return render_template('user_admin/index.html', users=users, metrics=metrics)

@user_admin_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')
def create():
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user_name = request.form.get('user_name', '').strip().upper()
        password = request.form.get('password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        organization_value = request.form.get('organization', '').strip()
        job_title = request.form.get('job_title', '').strip()
        phone = request.form.get('phone', '').strip()
        is_active = request.form.get('is_active') == 'on'
        
        if not email or not password or not user_name:
            flash('Email, user name, and password are required.', 'danger')
            agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
            custodians = Custodian.query.order_by(Custodian.custodian_name).all()
            return render_template('user_admin/create.html', 
                                 roles=Role.query.all(),
                                 warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                 agencies=agencies,
                                 custodians=custodians)
        
        if User.query.filter_by(email=email).first():
            flash('A user with this email already exists.', 'danger')
            agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
            custodians = Custodian.query.order_by(Custodian.custodian_name).all()
            return render_template('user_admin/create.html',
                                 roles=Role.query.all(),
                                 warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                 agencies=agencies,
                                 custodians=custodians)
        
        organization_name = None
        agency_id = None
        
        if organization_value:
            if ':' not in organization_value:
                flash('Invalid organization format. Please select from the dropdown.', 'danger')
                agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                return render_template('user_admin/create.html',
                                     roles=Role.query.all(),
                                     warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                     agencies=agencies,
                                     custodians=custodians)
            
            org_type, org_id = organization_value.split(':', 1)
            
            if org_type not in ['AGENCY', 'CUSTODIAN']:
                flash('Invalid organization type. Must be AGENCY or CUSTODIAN.', 'danger')
                agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                return render_template('user_admin/create.html',
                                     roles=Role.query.all(),
                                     warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                     agencies=agencies,
                                     custodians=custodians)
            
            if not org_id.isdigit():
                flash('Invalid organization ID format.', 'danger')
                agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                return render_template('user_admin/create.html',
                                     roles=Role.query.all(),
                                     warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                     agencies=agencies,
                                     custodians=custodians)
            
            if org_type == 'AGENCY':
                agency = Agency.query.filter_by(agency_id=int(org_id), status_code='A').first()
                if agency:
                    organization_name = agency.agency_name
                    agency_id = agency.agency_id
                else:
                    flash('Invalid agency selected.', 'danger')
                    agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                    return render_template('user_admin/create.html',
                                         roles=Role.query.all(),
                                         warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                         agencies=agencies,
                                         custodians=custodians)
            
            else:
                custodian = Custodian.query.filter_by(custodian_id=int(org_id)).first()
                if custodian:
                    organization_name = custodian.custodian_name
                    agency_id = None
                else:
                    flash('Invalid custodian selected.', 'danger')
                    agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                    return render_template('user_admin/create.html',
                                         roles=Role.query.all(),
                                         warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                         agencies=agencies,
                                         custodians=custodians)
        
        full_name = f"{first_name} {last_name}".strip()
        
        try:
            new_user = User(
                email=email,
                user_name=user_name,
                password_hash=generate_password_hash(password),
                first_name=first_name,
                last_name=last_name,
                full_name=full_name if full_name else None,
                organization=organization_name,
                agency_id=agency_id,
                job_title=job_title if job_title else None,
                phone=phone if phone else None,
                is_active=is_active
            )
            
            db.session.add(new_user)
            db.session.flush()
            
            role_ids = request.form.getlist('roles')
            for role_id in role_ids:
                user_role = UserRole(user_id=new_user.user_id, role_id=int(role_id))
                db.session.add(user_role)
            
            warehouse_ids = request.form.getlist('warehouses')
            for warehouse_id in warehouse_ids:
                user_warehouse = UserWarehouse(user_id=new_user.user_id, warehouse_id=int(warehouse_id))
                db.session.add(user_warehouse)
            
            db.session.commit()
            flash(f'User {email} created successfully.', 'success')
            return redirect(url_for('user_admin.index'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
            agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
            custodians = Custodian.query.order_by(Custodian.custodian_name).all()
            return render_template('user_admin/create.html',
                                 roles=Role.query.all(),
                                 warehouses=Warehouse.query.filter_by(status_code='A').all(),
                                 agencies=agencies,
                                 custodians=custodians)
    
    roles = Role.query.all()
    warehouses = Warehouse.query.filter_by(status_code='A').all()
    agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
    
    return render_template('user_admin/create.html', 
                         roles=roles, 
                         warehouses=warehouses,
                         agencies=agencies,
                         custodians=custodians)

@user_admin_bp.route('/<int:user_id>')
@login_required
@role_required('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')
def view(user_id):
    
    user = User.query.get_or_404(user_id)
    return render_template('user_admin/view.html', user=user)

@user_admin_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')
def edit(user_id):
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        if 'organization' not in request.form:
            flash('Organization field is required.', 'danger')
            agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
            custodians = Custodian.query.order_by(Custodian.custodian_name).all()
            roles = Role.query.all()
            warehouses = Warehouse.query.filter_by(status_code='A').all()
            user_role_ids = [r.id for r in user.roles]
            user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
            current_org_value = ''
            if user.agency_id:
                current_org_value = f'AGENCY:{user.agency_id}'
            elif user.organization:
                custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                if custodian:
                    current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
            return render_template('user_admin/edit.html',
                                 user=user,
                                 roles=roles,
                                 warehouses=warehouses,
                                 agencies=agencies,
                                 custodians=custodians,
                                 user_role_ids=user_role_ids,
                                 user_warehouse_ids=user_warehouse_ids,
                                 current_org_value=current_org_value)
        
        user_name = request.form.get('user_name', '').strip().upper()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        organization_value = request.form.get('organization', '').strip()
        job_title = request.form.get('job_title', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        is_active = request.form.get('is_active') == 'on'
        password = request.form.get('password', '').strip()
        
        if not user_name:
            flash('User name is required.', 'danger')
            agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
            custodians = Custodian.query.order_by(Custodian.custodian_name).all()
            roles = Role.query.all()
            warehouses = Warehouse.query.filter_by(status_code='A').all()
            user_role_ids = [r.id for r in user.roles]
            user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
            current_org_value = ''
            if user.agency_id:
                current_org_value = f'AGENCY:{user.agency_id}'
            elif user.organization:
                custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                if custodian:
                    current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
            return render_template('user_admin/edit.html',
                                 user=user,
                                 roles=roles,
                                 warehouses=warehouses,
                                 agencies=agencies,
                                 custodians=custodians,
                                 user_role_ids=user_role_ids,
                                 user_warehouse_ids=user_warehouse_ids,
                                 current_org_value=current_org_value)
        
        organization_name = None
        agency_id = None
        
        if organization_value:
            if ':' not in organization_value:
                flash('Invalid organization format. Please select from the dropdown.', 'danger')
                agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                roles = Role.query.all()
                warehouses = Warehouse.query.filter_by(status_code='A').all()
                user_role_ids = [r.id for r in user.roles]
                user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
                current_org_value = ''
                if user.agency_id:
                    current_org_value = f'AGENCY:{user.agency_id}'
                elif user.organization:
                    custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                    if custodian:
                        current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
                return render_template('user_admin/edit.html',
                                     user=user,
                                     roles=roles,
                                     warehouses=warehouses,
                                     agencies=agencies,
                                     custodians=custodians,
                                     user_role_ids=user_role_ids,
                                     user_warehouse_ids=user_warehouse_ids,
                                     current_org_value=current_org_value)
            
            org_type, org_id = organization_value.split(':', 1)
            
            if org_type not in ['AGENCY', 'CUSTODIAN']:
                flash('Invalid organization type. Must be AGENCY or CUSTODIAN.', 'danger')
                agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                roles = Role.query.all()
                warehouses = Warehouse.query.filter_by(status_code='A').all()
                user_role_ids = [r.id for r in user.roles]
                user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
                current_org_value = ''
                if user.agency_id:
                    current_org_value = f'AGENCY:{user.agency_id}'
                elif user.organization:
                    custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                    if custodian:
                        current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
                return render_template('user_admin/edit.html',
                                     user=user,
                                     roles=roles,
                                     warehouses=warehouses,
                                     agencies=agencies,
                                     custodians=custodians,
                                     user_role_ids=user_role_ids,
                                     user_warehouse_ids=user_warehouse_ids,
                                     current_org_value=current_org_value)
            
            if not org_id.isdigit():
                flash('Invalid organization ID format.', 'danger')
                agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                roles = Role.query.all()
                warehouses = Warehouse.query.filter_by(status_code='A').all()
                user_role_ids = [r.id for r in user.roles]
                user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
                current_org_value = ''
                if user.agency_id:
                    current_org_value = f'AGENCY:{user.agency_id}'
                elif user.organization:
                    custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                    if custodian:
                        current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
                return render_template('user_admin/edit.html',
                                     user=user,
                                     roles=roles,
                                     warehouses=warehouses,
                                     agencies=agencies,
                                     custodians=custodians,
                                     user_role_ids=user_role_ids,
                                     user_warehouse_ids=user_warehouse_ids,
                                     current_org_value=current_org_value)
            
            if org_type == 'AGENCY':
                agency = Agency.query.filter_by(agency_id=int(org_id), status_code='A').first()
                if agency:
                    organization_name = agency.agency_name
                    agency_id = agency.agency_id
                else:
                    flash('Invalid agency selected.', 'danger')
                    agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                    roles = Role.query.all()
                    warehouses = Warehouse.query.filter_by(status_code='A').all()
                    user_role_ids = [r.id for r in user.roles]
                    user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
                    current_org_value = ''
                    if user.agency_id:
                        current_org_value = f'AGENCY:{user.agency_id}'
                    elif user.organization:
                        custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                        if custodian:
                            current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
                    return render_template('user_admin/edit.html',
                                         user=user,
                                         roles=roles,
                                         warehouses=warehouses,
                                         agencies=agencies,
                                         custodians=custodians,
                                         user_role_ids=user_role_ids,
                                         user_warehouse_ids=user_warehouse_ids,
                                         current_org_value=current_org_value)
            
            else:
                custodian = Custodian.query.filter_by(custodian_id=int(org_id)).first()
                if custodian:
                    organization_name = custodian.custodian_name
                    agency_id = None
                else:
                    flash('Invalid custodian selected.', 'danger')
                    agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
                    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
                    roles = Role.query.all()
                    warehouses = Warehouse.query.filter_by(status_code='A').all()
                    user_role_ids = [r.id for r in user.roles]
                    user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
                    current_org_value = ''
                    if user.agency_id:
                        current_org_value = f'AGENCY:{user.agency_id}'
                    elif user.organization:
                        custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                        if custodian:
                            current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
                    return render_template('user_admin/edit.html',
                                         user=user,
                                         roles=roles,
                                         warehouses=warehouses,
                                         agencies=agencies,
                                         custodians=custodians,
                                         user_role_ids=user_role_ids,
                                         user_warehouse_ids=user_warehouse_ids,
                                         current_org_value=current_org_value)
        
        try:
            user.user_name = user_name
            user.first_name = first_name
            user.last_name = last_name
            user.organization = organization_name
            user.agency_id = agency_id
            user.job_title = job_title
            user.phone = phone
            user.is_active = is_active
            
            full_name = f"{first_name} {last_name}".strip()
            user.full_name = full_name if full_name else None
            
            if password:
                user.password_hash = generate_password_hash(password)
            
            UserRole.query.filter_by(user_id=user.user_id).delete()
            role_ids = request.form.getlist('roles')
            for role_id in role_ids:
                user_role = UserRole(user_id=user.user_id, role_id=int(role_id))
                db.session.add(user_role)
            
            UserWarehouse.query.filter_by(user_id=user.user_id).delete()
            warehouse_ids = request.form.getlist('warehouses')
            for warehouse_id in warehouse_ids:
                user_warehouse = UserWarehouse(user_id=user.user_id, warehouse_id=int(warehouse_id))
                db.session.add(user_warehouse)
            
            db.session.commit()
            flash(f'User {user.email} updated successfully.', 'success')
            return redirect(url_for('user_admin.view', user_id=user.user_id))
        
        except Exception as e:
            db.session.rollback()
            db.session.refresh(user)
            flash(f'Error updating user: {str(e)}', 'danger')
            agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
            custodians = Custodian.query.order_by(Custodian.custodian_name).all()
            roles = Role.query.all()
            warehouses = Warehouse.query.filter_by(status_code='A').all()
            user_role_ids = [r.id for r in user.roles]
            user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
            current_org_value = ''
            if user.agency_id:
                current_org_value = f'AGENCY:{user.agency_id}'
            elif user.organization:
                custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
                if custodian:
                    current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
            return render_template('user_admin/edit.html',
                                 user=user,
                                 roles=roles,
                                 warehouses=warehouses,
                                 agencies=agencies,
                                 custodians=custodians,
                                 user_role_ids=user_role_ids,
                                 user_warehouse_ids=user_warehouse_ids,
                                 current_org_value=current_org_value)
    
    roles = Role.query.all()
    warehouses = Warehouse.query.filter_by(status_code='A').all()
    agencies = Agency.query.filter_by(status_code='A').order_by(Agency.agency_name).all()
    custodians = Custodian.query.order_by(Custodian.custodian_name).all()
    user_role_ids = [r.id for r in user.roles]
    user_warehouse_ids = [w.warehouse_id for w in user.warehouses]
    
    current_org_value = ''
    if user.agency_id:
        current_org_value = f'AGENCY:{user.agency_id}'
    elif user.organization:
        custodian = Custodian.query.filter_by(custodian_name=user.organization).first()
        if custodian:
            current_org_value = f'CUSTODIAN:{custodian.custodian_id}'
    
    return render_template('user_admin/edit.html', 
                         user=user, 
                         roles=roles, 
                         warehouses=warehouses,
                         agencies=agencies,
                         custodians=custodians,
                         user_role_ids=user_role_ids,
                         user_warehouse_ids=user_warehouse_ids,
                         current_org_value=current_org_value)

@user_admin_bp.route('/<int:user_id>/deactivate', methods=['POST'])
@login_required
@role_required('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')
def deactivate(user_id):
    
    if user_id == current_user.user_id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('user_admin.view', user_id=user_id))
    
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    
    flash(f'User {user.email} has been deactivated.', 'success')
    return redirect(url_for('user_admin.index'))

@user_admin_bp.route('/<int:user_id>/activate', methods=['POST'])
@login_required
@role_required('SYSTEM_ADMINISTRATOR', 'SYS_ADMIN')
def activate(user_id):
    
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    
    flash(f'User {user.email} has been activated.', 'success')
    return redirect(url_for('user_admin.index'))
