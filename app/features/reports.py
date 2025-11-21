from flask import Blueprint, render_template, Response
from flask_login import login_required
from sqlalchemy import func
from app.db.models import db, Inventory, Item, Warehouse, Event, Donor, Donation, DonationIntakeItem
from datetime import datetime
import csv
from io import StringIO
from app.utils.timezone import now as jamaica_now

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')

@reports_bp.route('/inventory_summary')
@login_required
def inventory_summary():
    summary = db.session.query(
        Warehouse.warehouse_name,
        Item.item_name,
        func.sum(Inventory.usable_qty).label('usable'),
        func.sum(Inventory.reserved_qty).label('reserved'),
        func.sum(Inventory.defective_qty).label('defective'),
        func.sum(Inventory.expired_qty).label('expired')
    ).join(
        Inventory, Warehouse.warehouse_id == Inventory.inventory_id
    ).join(
        Item, Inventory.item_id == Item.item_id
    ).group_by(
        Warehouse.warehouse_name, Item.item_name
    ).all()
    
    return render_template('reports/inventory_summary.html', summary=summary)

@reports_bp.route('/inventory_summary/export')
@login_required
def export_inventory():
    summary = db.session.query(
        Warehouse.warehouse_name,
        Item.item_name,
        func.sum(Inventory.usable_qty).label('usable'),
        func.sum(Inventory.reserved_qty).label('reserved'),
        func.sum(Inventory.defective_qty).label('defective'),
        func.sum(Inventory.expired_qty).label('expired')
    ).join(
        Inventory, Warehouse.warehouse_id == Inventory.inventory_id
    ).join(
        Item, Inventory.item_id == Item.item_id
    ).group_by(
        Warehouse.warehouse_name, Item.item_name
    ).all()
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Warehouse', 'Item', 'Usable Qty', 'Reserved Qty', 'Defective Qty', 'Expired Qty'])
    
    for row in summary:
        writer.writerow([row.warehouse_name, row.item_name, 
                        float(row.usable or 0), float(row.reserved or 0),
                        float(row.defective or 0), float(row.expired or 0)])
    
    output = si.getvalue()
    si.close()
    
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=inventory_summary_{jamaica_now().strftime("%Y%m%d_%H%M%S")}.csv'}
    )

@reports_bp.route('/donations_summary')
@login_required
def donations_summary():
    # Calculate total value from DonationIntakeItem (quantity * unit value)
    donations = db.session.query(
        Donor.donor_name,
        func.count(func.distinct(Donation.donation_id)).label('donation_count'),
        func.sum(
            (DonationIntakeItem.usable_qty + 
             DonationIntakeItem.defective_qty + 
             DonationIntakeItem.expired_qty) * 
            DonationIntakeItem.avg_unit_value
        ).label('total_value')
    ).join(
        Donation, Donor.donor_id == Donation.donor_id
    ).outerjoin(
        DonationIntakeItem, Donation.donation_id == DonationIntakeItem.donation_id
    ).group_by(
        Donor.donor_name
    ).order_by(
        func.sum(
            (DonationIntakeItem.usable_qty + 
             DonationIntakeItem.defective_qty + 
             DonationIntakeItem.expired_qty) * 
            DonationIntakeItem.avg_unit_value
        ).desc()
    ).all()
    
    return render_template('reports/donations_summary.html', donations=donations)
