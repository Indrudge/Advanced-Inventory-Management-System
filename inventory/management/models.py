from django.db import models

from django.conf import settings

CUSTOMERS_COLLECTION = settings.CUSTOMERS_COLLECTION
WORKPLACES_COLLECTION = settings.WORKPLACES_COLLECTION

# Create your models here.
    
class CustomerModel:
    def __init__(self):
        self.collection = CUSTOMERS_COLLECTION

    def create_customer(self, email, phone, hashed_password):
        self.collection.insert_one({
            "email": email,
            "phone": phone,
            "password": hashed_password
        })

    def find_customer(self, email):
        return self.collection.find_one({"email": email})



class WorkplaceModel:
    def __init__(self):
        self.collection = WORKPLACES_COLLECTION

    def create_workplace(self, name, email, address, workplace_type, inventory_type, password):
        workplace = {
            "name": name,
            "email": email,
            "address": address,
            "workplace_type": workplace_type,
            "inventory_type": inventory_type,
            "password": password,  # Hash this in production
        }
        self.collection.insert_one(workplace)
        return workplace

    def find_workplace(self, email):
        return self.collection.find_one({"email": email})
    
    