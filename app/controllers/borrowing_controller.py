from flask import  request,render_template
from flask import jsonify
import os
import uuid
from datetime import datetime

from config import Config
from app.models.inventory_models import Inventory
from app.models.borrowing_models import Borrowing
from app.models.borrowing_details_model import BorrowingDetails
from app.services.services import CRUDService

inventory_service = CRUDService(Inventory)
borrowing_service = CRUDService(Borrowing)
cancel_service = CRUDService(BorrowingDetails)


def report(request):
    borrowing_list = Borrowing.query.all() 
    borrowings = [] 
    for borrowing in borrowing_list:
        borrowing.inventory_item = borrowing.cart_items[0].inventory_item if borrowing.cart_items else None  

          
        if borrowing.get_cart_items:
            borrowing.inventory_titles = [
                f"{cart_item.inventory_item.title.capitalize()} (Qty: {cart_item.quantity})"
                for cart_item in borrowing.cart_items if cart_item.inventory_item
            ]
        else:
            borrowing.inventory_titles = []
    return render_template('admin/reports.html', borrowings=borrowing_list)


def borrowings(request, item_uuid=None):
   if request.method == 'GET':
        now = datetime.utcnow()
        auto_cancel_expired_borrowings()

        borrowing_list = Borrowing.query.all()  
        borrowings = [] 
        for borrowing in borrowing_list:
            borrowing.inventory_item = borrowing.cart_items[0].inventory_item if borrowing.cart_items else None  

            if borrowing.end_date:
                delta_days = (borrowing.end_date.date() - now.date()).days
                
                if delta_days >= 0:
                    borrowing.days_remaining = delta_days
                    borrowing.days_late = 0
                else:
                    borrowing.days_remaining = 0
                    borrowing.days_late = abs(delta_days)  # Correctly store overdue days
            else:
                borrowing.days_remaining = None
                borrowing.days_late = None


            if borrowing.get_cart_items:
               borrowing.inventory_titles = [
                    f"{cart_item.inventory_item.title.capitalize()} (Qty: {cart_item.quantity})"
                    for cart_item in borrowing.cart_items if cart_item.inventory_item
                ]
            else:
                borrowing.inventory_titles = [] 

        return render_template('admin/borrowing.html', borrowings=borrowing_list)
    
def borrowings_status(request, borrowing_id=None):
    if request.method != 'PUT':
        return jsonify({'error': True, 'message': 'Invalid Method'}), 400

    borrowing = borrowing_service.get_one(id=borrowing_id)

    if not borrowing:
        return jsonify({'success': False, 'message': 'Borrowing record not found'}), 404

    data = request.json
    new_status = data.get("status")

    for cart_item in borrowing.cart_items:
        inventory = inventory_service.get_one(id=cart_item.inventory_id)  # Get inventory item

        if not inventory:
            return jsonify({'success': False, 'message': f'Inventory ID {cart_item.inventory_id} not found'}), 404

        # inventory.quantity += cart_item.quantity

        if inventory.quantity > 0:
            inventory.status = 'available'

        inventory_service.update(inventory)

    
    borrowing_service.update(borrowing.id, status=new_status)

    return jsonify({'success': True, 'message': 'Borrowing request updated successfully'}), 200


def borrowings_done(request, borrowing_id=None):
    if request.method == 'PUT':
        now = datetime.utcnow()
        borrowing = borrowing_service.get_one(id=borrowing_id)

        if not borrowing:
            return jsonify({'success': False, 'message': 'Borrowing record not found'}), 404
        
        data = request.json
        new_status = data.get("status")
        
        for cart_item in borrowing.cart_items:
            inventory = inventory_service.get_one(id=cart_item.inventory_id)  

            if not inventory:
                return jsonify({'success': False, 'message': f'Inventory ID {cart_item.inventory_id} not found'}), 404

            inventory.quantity += cart_item.quantity

            if inventory.quantity > 0:
                inventory.status = 'available'

            inventory_service.update(inventory)

        if new_status == "completed":
            borrowing.return_date = now
            
        borrowing_service.update(borrowing.id, status=new_status, return_date=borrowing.return_date)
        return jsonify({'success': True, 'message': 'Borrowing completed'}), 200
    return jsonify({'error': False, 'message': 'Invalid Method'}), 400



def borrowings_cancel_reason(request, borrowing_id=None):
    if request.method == 'PUT':
        borrowing = borrowing_service.get_one(id=borrowing_id)

        if not borrowing:
            return jsonify({'success': False, 'message': 'Borrowing record not found'}), 404
        
        data = request.json
        new_status = data.get("status")
        reason = data.get("reason")
        if new_status != "cancelled":
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        for cart_item in borrowing.cart_items:
            inventory = inventory_service.get_one(id=cart_item.inventory_id)  

            if not inventory:
                return jsonify({'success': False, 'message': f'Inventory ID {cart_item.inventory_id} not found'}), 404

            inventory.quantity += cart_item.quantity

            if inventory.quantity > 0:
                inventory.status = 'available'

            inventory_service.update(inventory)

        
        borrowing_service.update(borrowing.id, status=new_status)
        cancel_service.create(borrowing_id=borrowing.id, cancel_reason=reason)
        return jsonify({'success': True, 'message': 'Borrowing request canceled'}), 200
    return jsonify({'error': False, 'message': 'Invalid Method'}), 400

def auto_cancel_expired_borrowings():
    now = datetime.utcnow()
    expired_borrowings = borrowing_service.get(status='pending')
    
    cancelled_count = 0
    for borrowing in expired_borrowings:
       
        if borrowing.end_date and borrowing.end_date < now:
            # Return inventory items to stock
            for cart_item in borrowing.cart_items:
                inventory = inventory_service.get_one(id=cart_item.inventory_id)
                if inventory:
                    inventory.quantity += cart_item.quantity
                    inventory.status = 'available' if inventory.quantity > 0 else inventory.status
                    inventory_service.update(inventory)

            # Cancel borrowing
            borrowing_service.update(borrowing.id, status="cancelled")
            cancel_service.create(borrowing_id=borrowing.id, cancel_reason="Auto-cancelled due to expiration")
            cancelled_count += 1

    return jsonify({'success': True, 'message': f'Auto-cancelled {cancelled_count} expired borrowings'}), 200


def borrowings_cancel(request, borrowing_id=None):
    if request.method == 'PUT':
        borrowing = borrowing_service.get_one(id=borrowing_id)

        if not borrowing:
            return jsonify({'success': False, 'message': 'Borrowing record not found'}), 404
        
        data = request.json
        new_status = data.get("status")
        if new_status != "cancelled":
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        for cart_item in borrowing.cart_items:
            inventory = inventory_service.get_one(id=cart_item.inventory_id)  

            if not inventory:
                return jsonify({'success': False, 'message': f'Inventory ID {cart_item.inventory_id} not found'}), 404

            inventory.quantity += cart_item.quantity

            if inventory.quantity > 0:
                inventory.status = 'available'

            inventory_service.update(inventory)

        
        borrowing_service.update(borrowing.id, status=new_status)
        cancel_service.create(borrowing_id=borrowing.id)
        return jsonify({'success': True, 'message': 'Borrowing request canceled'}), 200
    return jsonify({'error': False, 'message': 'Invalid Method'}), 400