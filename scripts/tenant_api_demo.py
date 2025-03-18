#!/usr/bin/env python
import requests
import json
from datetime import datetime, timedelta
import sys
import os

# Add the parent directory to the path so we can import modules from the main project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Base URL - Update this with your server's URL
BASE_URL = "http://localhost:8000"

def add_tenant():
    """Add a new tenant-tester to the database using the API"""
    url = f"{BASE_URL}/api/tenants/"
    
    # Current date and future dates for the tenant
    today = datetime.today().date()
    move_in_date = today
    move_out_date = (today + timedelta(days=365)).isoformat()  # One year from now
    probation_end = (today + timedelta(days=90)).isoformat()   # 90 days from now
    
    # Prepare tenant data
    tenant_data = {
        "birthday": "1990-01-01",
        "current_floor": "1",
        "current_points": "0.00",
        "current_room": "101",
        "deposit": "500.00",
        "email": "tenant-tester@example.com",
        "extension": 0,
        "external_id": "tenant-tester-ext-id",
        "gender": "Other",
        "move_in": move_in_date.isoformat(),
        "move_out": move_out_date,
        "name": "Tenant",
        "nationality": "Global",
        "note": "Test tenant created via API",
        "probation_end": probation_end,
        "study_field": "Computer Science",
        "sublet": 0.0,
        "surname": "Tester",
        "tel_number": "+1234567890",
        "university": "Test University",
        "username": "tenant-tester"
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Send POST request to create tenant
    response = requests.post(url, data=json.dumps(tenant_data), headers=headers)
    
    if response.status_code == 201:
        print("✅ Tenant created successfully!")
        print(f"Tenant ID: {response.json()['id']}")
        return response.json()['id']
    else:
        print("❌ Failed to create tenant")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return None

def remove_tenant(tenant_id):
    """Remove a tenant from the database using the API"""
    url = f"{BASE_URL}/api/tenants/{tenant_id}/"
    
    # Send DELETE request to remove tenant
    response = requests.delete(url)
    
    if response.status_code == 204:
        print(f"✅ Tenant with ID {tenant_id} deleted successfully!")
        return True
    else:
        print(f"❌ Failed to delete tenant with ID {tenant_id}")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def main():
    print("=== Tenant API Demo ===")
    print("1. Adding tenant-tester...")
    tenant_id = add_tenant()
    
    if tenant_id:
        print("\n2. Getting all tenants (to verify addition)...")
        response = requests.get(f"{BASE_URL}/api/tenants/")
        tenants = response.json()
        print(f"Number of tenants: {len(tenants)}")
        
        input("\nPress Enter to delete the tenant-tester...")
        
        print("\n3. Removing tenant-tester...")
        remove_tenant(tenant_id)
    
    print("\nDemo completed!")

if __name__ == "__main__":
    main() 