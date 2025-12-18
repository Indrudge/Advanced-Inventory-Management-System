from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
from django.contrib import messages
from datetime import datetime, timedelta
from django.utils.timezone import now
import subprocess
import uuid
from bson import ObjectId
import os
import json
import matplotlib.pyplot as plt
from pymongo import MongoClient
from .models import CustomerModel, WorkplaceModel
from dateutil.parser import parse as parse_iso_date

# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")
main_db = client["workplaces"]  # Main DB storing all workspace details

# Home page view
def home(request):
    return render(request, 'index.html')




# -------------------- Workplace Views -------------------- #
def workplace_register(request):
    """Handles workplace registration."""
    if request.method == "POST":
        name = request.POST["name"]
        email = request.POST["email"]
        address = request.POST["address"]
        workplace_type = request.POST["workplace_type"]
        inventory_type = request.POST["inventory_type"]
        password = make_password(request.POST["password"])  # Hash password before storing

        workplace_model = WorkplaceModel()
        
        # Check if workplace already exists
        existing_workplace = workplace_model.find_workplace(email)
        if existing_workplace:
            return render(request, "workplace_register.html", {"error": "Email already registered"})

        # Store workplace details
        workplace_model.create_workplace(name, email, address, workplace_type, inventory_type, password)

        # Create a new MongoDB database for this workplace
        client[name].create_collection("sales")
        client[name].create_collection("inventory")
        client[name].create_collection("items")

        return redirect("workplace_login")  # Redirect to workplace login page
    
    return render(request, "workplace_register.html")

def workplace_login(request):
    """Handles workplace login authentication."""
    if request.method == "POST":
        email = request.POST["email"]
        password = request.POST["password"]

        workplace_model = WorkplaceModel()
        workplace = workplace_model.find_workplace(email)

        if workplace and check_password(password, workplace["password"]):
            request.session["user_type"] = "workplace"
            request.session["email"] = email
            request.session["workspace"] = workplace["name"]

            return redirect("dashboard")  # Redirect to dashboard
        
        return render(request, "workplace_login.html", {"error": "Invalid credentials"})
    
    return render(request, "workplace_login.html")

def dashboard(request):
    """Renders the dashboard page for workplaces."""
    workspace = request.session.get("workspace")
    if not workspace:
        return redirect("workplace_login")
    
    return render(request, "dashboard.html", {"workspace": workspace})

# -------------------- Inventory Management -------------------- #
def get_inventory_items(request):
    """Fetches all inventory items for the logged-in workspace."""
    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)

    inventory_items = list(client[workspace]["inventory"].find({}, {"_id": 0, "name": 1, "quantity": 1}))
    return JsonResponse({"items": inventory_items})

def get_items(request):
    """Fetches all items with SKU, item name, category, size, price, and item ID for the logged-in workspace."""
    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)

    items = list(client[workspace]["items"].find({}, {"_id": 0, "sku": 1, "item_name": 1, "item_cat": 1, "item_size": 1, "item_price": 1, "item_id": 1}))
    return JsonResponse({"items": items})

@csrf_exempt
def add_inventory(request):
    """Adds or updates an inventory item."""
    if request.method == "POST":
        workspace = request.session.get("workspace")
        if not workspace:
            return JsonResponse({"error": "Not logged in"}, status=401)
        
        item = request.POST.get("item")
        item_type = request.POST.get("item_type")
        quantity = int(request.POST.get("quantity", 0))

        db = client[workspace]
        db.inventory.update_one(
            {"name": item},
            {"$inc": {"quantity": quantity}, "$setOnInsert": {"item_type": item_type}},
            upsert=True
        )
        
        return JsonResponse({"message": "Inventory updated successfully"})
    
    return JsonResponse({"error": "Invalid request"}, status=400)

# -------------------- Sales Management -------------------- #
def get_next_order_id(db):
    counter = db.counters.find_one_and_update(
        {"_id": "order_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    next_seq = counter["seq"]
    return f"ORD{next_seq:03d}"  # e.g., ORD001, ORD002

@csrf_exempt
def add_sale(request):
    """Records a new sale with multiple items, deducts ingredients, and stores individual order records."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)

    db = client[workspace]

    try:
        data = json.loads(request.body)
        cust_name = data.get("cust_name")
        in_or_out = data.get("in_or_out")  # "dine-in" or "takeout"
        items = data.get("items", [])

        if not all([cust_name, in_or_out, items]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        order_id = get_next_order_id(db)

        for entry in items:
            item_name = entry.get("item_name")
            quantity = int(entry.get("quantity", 0))

            if not item_name or quantity <= 0:
                return JsonResponse({"error": f"Invalid item or quantity: {item_name}"}, status=400)

            # Step 1: Get item details
            item = db.items.find_one({"item_name": item_name})
            if not item:
                return JsonResponse({"error": f"Item not found: {item_name}"}, status=404)

            item_id = item.get("item_id")
            sku = item.get("sku")
            if not sku:
                return JsonResponse({"error": f"SKU not found for item: {item_name}"}, status=500)

            # Step 2: Get recipe for item - This will return all ingredients for the SKU
            recipe_items = list(db.recipe.find({"sku": sku}))
            if not recipe_items:
                return JsonResponse({"error": f"No recipe found for item: {item_name}"}, status=404)

            # Step 3: Check inventory for each ingredient
            for recipe_item in recipe_items:
                ing_id = recipe_item.get("ing_id")
                req_qty_per_item = recipe_item.get("quantity", 0)
                total_required_qty = req_qty_per_item * quantity

                inventory_item = db.inventory.find_one({"ing_id": ing_id})
                if not inventory_item or inventory_item.get("quantity", 0) < total_required_qty:
                    return JsonResponse({"error": f"Not enough stock for ingredient: {ing_id}"}, status=400)

            # Step 4: Deduct inventory for each ingredient
            for recipe_item in recipe_items:
                ing_id = recipe_item["ing_id"]
                total_required_qty = recipe_item["quantity"] * quantity
                db.inventory.update_one(
                    {"ing_id": ing_id},
                    {"$inc": {"quantity": -total_required_qty}}
                )

            # Step 5: Insert order record into the orders collection
            order_record = {
                "row_id": str(uuid.uuid4()),
                "order_id": order_id,
                "date": now().isoformat(),
                "item_id": item_id,
                "item_name": item_name,
                "quantity": quantity,
                "cust_name": cust_name,
                "in_or_out": in_or_out
            }
            db.orders.insert_one(order_record)

        return JsonResponse({"message": "Sale recorded successfully", "order_id": order_id})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)




        # -------------------- Workspace & Menu Views -------------------- #
def get_workspaces(request):
    """Fetches all registered workspaces."""
    workspaces = list(main_db["workplace_details"].find({}, {"_id": 0}))
    return JsonResponse({"workspaces": workspaces})



# -------------------- Sales & Inventory Stats -------------------- #



def get_sales_stats(request):
    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)

    db = client[workspace]

    now = datetime.utcnow()
    week_ago = now - timedelta(days=6)  # last 7 days including today
    week_days = [(now - timedelta(days=i)).date() for i in range(6, -1, -1)]  # Mon to Sun

    def parse_date(order):
        if "date" in order:
            try:
                if isinstance(order["date"], str):
                    try:
                        # Try parsing ISO 8601 string like: "2025-05-02T18:47:28.470091+00:00"
                        return parse_iso_date(order["date"]).date()
                    except:
                        # Fallback: try old format like "24/02/17 13:10"
                        return datetime.strptime(order["date"], "%d/%m/%y %H:%M").date()
                elif isinstance(order["date"], datetime):
                    return order["date"].date()
            except:
                return None
        elif "created_at" in order:
            try:
                return order["created_at"].date()
            except:
                return None
        return None

    # Fetch all orders and parse dates
    all_orders = list(db.orders.find({}))
    sales_this_week = {day.strftime("%a"): 0 for day in week_days}
    sales_month = 0
    sales_year = 0
    total_sales = 0

    for order in all_orders:
        date = parse_date(order)
        if not date:
            continue
        quantity = order.get("quantity", 0)

        # Weekly
        if week_ago.date() <= date <= now.date():
            day_label = date.strftime("%a")
            sales_this_week[day_label] += quantity

        # Monthly
        if date.month == now.month and date.year == now.year:
            sales_month += quantity

        # Yearly
        if date.year == now.year:
            sales_year += quantity

        # Overall
        total_sales += quantity

    return JsonResponse({
        "weekly_sales": sales_this_week,
        "sales_month": sales_month,
        "sales_year": sales_year,
        "sales_total": total_sales
    })






def get_inventory_stats(request):
    """Fetches inventory statistics: total items, out-of-stock count, and low-stock count."""
    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)
    
    db = client[workspace]
    inventory = list(db.inventory.find())
    
    stats = {
        "total_items": len(inventory),
        "out_of_stock": sum(1 for item in inventory if item.get("quantity", 0) <= 0),
        "low_stock": sum(1 for item in inventory if 0 < item.get("quantity", 0) < 10)
    }
    
    return JsonResponse(stats)

# -------------------- Data Visualization -------------------- #

# Example sales data endpoint
def get_sales_data(request):
    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)
    
    db = client[workspace]
    
    # Perform aggregation to calculate total sales per item
    sales_data = db.orders.aggregate([
        # Lookup to join the orders with the items collection based on item_id
        {
            "$lookup": {
                "from": "items",              # Collection to join
                "localField": "item_id",      # Field in the orders collection
                "foreignField": "_id",        # Field in the items collection
                "as": "item_details"          # Alias for the joined items data
            }
        },
        # Unwind the item_details array to simplify access to item data
        {
            "$unwind": "$item_details"
        },
        # Calculate the total sales amount for each order (quantity * price)
        {
            "$addFields": {
                "sales_amount_calculated": {
                    "$multiply": ["$quantity", "$item_details.price"]
                }
            }
        },
        # Group by item name and sum up the sales amounts
        {
            "$group": {
                "_id": "$item_details.name",   # Group by item name
                "total_sales": {"$sum": "$sales_amount_calculated"}  # Sum the sales amount
            }
        },
        # Sort the items by total sales in descending order
        {
            "$sort": {"total_sales": -1}
        }
    ])

    # Convert the aggregation result into a list and return it
    sales_data = list(sales_data)
    
    return JsonResponse({"sales_data": sales_data})


#  inventory data endpoint
def get_inventory_data(request):
    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)
    
    db = client[workspace]
    
    # Fetch inventory data
    inventory_data = list(db.inventory.find({}, {"_id": 0, "ing_id": 1, "name": 1, "quantity": 1}))  # You can adjust the query to group by ingredient type
    
    name = []
    inventory = []
    labels = []
    for item in inventory_data:
        name.append(item["name"])
        labels.append(item["ing_id"])  # Ingredient IDs or names
        inventory.append(item["quantity"])  # Inventory quantity
    
    return JsonResponse({"labels": labels, "inventory": inventory, "name" : name })

def get_sales_distribution(request):
    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)
    
    db = client[workspace]
    
    # Aggregation to count the number of orders grouped by order type (Dine-In, Takeout)
    sales_data = db.orders.aggregate([
        {
            "$group": {
                "_id": "$in_or_out",  # Group by 'order_type' (Dine-In, Takeout, etc.)
                "order_count": {"$sum": 1}  # Count the number of orders for each type
            }
        },
        {
            "$match": {
                "_id": {"$in": ["dine-in", "takeout"]}  # Filter to only include Dine-In and Takeout
            }
        }
    ])
    
    # Convert the aggregated data to a dictionary format
    result = {
        "sales_types": {data["_id"]: data["order_count"] for data in sales_data}
    }
    
    return JsonResponse(result)




@csrf_exempt
def get_inventory_restocking_recommendations(request):

    workspace = request.session.get("workspace")
    if not workspace:
        return JsonResponse({"error": "Not logged in"}, status=401)

    try:

        subprocess.run([
            r'C:\Volume_d\sem6BCA\MajorP2\projest\mjp2\Scripts\python.exe',
            r'C:\Volume_d\sem6BCA\MajorP2\projest\Major2\inventory\management\mlload.py'
        ], check=True)

        db = client[workspace]
        predictions_col = db["prediction"]
        items_col = db["items"]
        recipe_col = db["recipe"]
        inventory_col = db["inventory"]

        predictions = list(predictions_col.find())

        restocking_recommendations = []
        item_sales_predictions = []
        seen_ing_ids = set()  # Track already added ingredient IDs

        for pred in predictions:
            item_id = pred["item_id"]
            predicted_qty = pred["predicted_quantity"]

            item = items_col.find_one({"item_id": item_id})
            if not item:
                continue

            sku = item.get("sku")
            item_name = item.get("item_name", "Unknown")
            item_size = item.get("item_size", "Unknown")

            item_sales_predictions.append({
                "item_id": item_id,
                "item_name": item_name,
                "item_size": item_size,
                "predicted_quantity": predicted_qty
            })

            recipe_entries = list(recipe_col.find({"sku": sku}))
            for entry in recipe_entries:
                ing_id = entry["ing_id"]
                qty_per_item = entry["quantity"]
                total_needed = predicted_qty * qty_per_item

                if ing_id in seen_ing_ids:
                    continue  # Skip if already added

                inv = inventory_col.find_one({"ing_id": ing_id})
                if not inv:
                    continue

                current_stock = inv.get("quantity", 0)
                shortage = max(0, total_needed - current_stock)

                if shortage > 0:
                    seen_ing_ids.add(ing_id)
                    restocking_recommendations.append({
                        "ing_id": ing_id,
                        "ing_name": inv.get("name", "Unknown Ingredient"),
                        "inv_id": inv.get("inv_id", "N/A"),
                        "current_stock": current_stock,
                        "predicted_usage": total_needed,
                        "shortage": shortage,
                        "unit": inv.get("ing_meas", "")
                    })

        return JsonResponse({
            "item_sales_predictions": item_sales_predictions,
            "restocking_recommendations": restocking_recommendations
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def prediction_page(request):
    workspace = request.session.get("workspace")
    if not workspace:
        return redirect("login")  # Or any fallback

    return render(request, "prediction.html")


# shop 
#   # Shared database for all customers and workspaces




# Connect to main MongoDB

# def customer_register(request):
#     """Handles customer registration securely."""
#     if request.method == "POST":
#         email = request.POST["email"]
#         phone = request.POST["phone"]
#         raw_password = request.POST["password"]
#         hashed_password = make_password(raw_password)

#         customer_model = CustomerModel()

#         # Check if customer already exists
#         existing_customer = customer_model.find_customer(email)
#         if existing_customer:
#             return render(request, "customer_register.html", {"error": "Email already registered"})

#         # Save new customer
#         customer_model.create_customer(email, phone, hashed_password)
#         return redirect("customer_login")

#     return render(request, "customer_register.html")


# def customer_login(request):
#     """Handles customer login authentication securely."""
#     if request.method == "POST":
#         email = request.POST["email"]
#         password = request.POST["password"]

#         customer_model = CustomerModel()
#         customer = customer_model.find_customer(email)

#         if customer and check_password(password, customer["password"]):
#             request.session["user_type"] = "customer"
#             request.session["email"] = email
#             return redirect("customer_home")

#         return render(request, "customer_login.html", {"error": "Invalid email or password"})

#     return render(request, "customer_login.html")

# def customer_home(request):
#     """Displays all workspaces and their offerings."""
#     # email = request.session.get("email")
#     # if not email:
#     #     return JsonResponse({"error": "Customer not logged in"}, status=401)

#     # customer = main_db["customer"].find_one({"email": email})
#     # if not customer:
#     #     return JsonResponse({"error": "Customer not found"}, status=404)

#     workspaces = list(main_db["workspace"].find({}, {
#         "_id": 0,
#         "name": 1,
#         "address": 1,
#         "workplace_type": 1,
#         "inventory_type": 1
#     }))

#     return render(request, "customer_home.html", {
#         "customer": ["email"],
#         "workspaces": workspaces
#     })

# def workspace_items(request, workspace_name):
#     """Shows items available at a specific workspace."""
#     email = request.session.get("email")
#     if not email:
#         return JsonResponse({"error": "Customer not logged in"}, status=401)

#     workspace = main_db["workspace"].find_one({"name": workspace_name})
#     if not workspace:
#         return JsonResponse({"error": "Workspace not found"}, status=404)

#     items = list(main_db[workspace_name].find({"_id": 0}))  # Get items from workspace's specific database

#     return render(request, "workspace_items.html", {
#         "workspace": workspace_name,
#         "items": items
#     })

# def add_to_cart(request, item_id):
#     """Add an item to the customer's cart."""
#     email = request.session.get("email")
#     if not email:
#         return JsonResponse({"error": "Customer not logged in"}, status=401)

#     quantity = int(request.POST["quantity"])

#     # Get customer cart or initialize it
#     cart = request.session.get("cart", {})
#     cart[item_id] = cart.get(item_id, 0) + quantity
#     request.session["cart"] = cart

#     return redirect("view_cart")


# def view_cart(request):
#     """Display the items in the customer's cart."""
#     email = request.session.get("email")
#     if not email:
#         return JsonResponse({"error": "Customer not logged in"}, status=401)

#     cart = request.session.get("cart", {})
#     items = []
#     for item_id, quantity in cart.items():
#         item = main_db["items"].find_one({"item_id": item_id})
#         items.append({"item": item, "quantity": quantity})

#     return render(request, "view_cart.html", {"items": items, "cart": cart})

# def checkout(request):
#     """Proceed to checkout and place the order."""
#     email = request.session.get("email")
#     if not email:
#         return JsonResponse({"error": "Customer not logged in"}, status=401)

#     cart = request.session.get("cart", {})
#     items = []
#     for item_id, quantity in cart.items():
#         item = main_db["items"].find_one({"item_id": item_id})
#         items.append({"item": item, "quantity": quantity})

#     if request.method == "POST":
#         # Place the order logic here (e.g., saving to a database)
#         # Clear cart after placing the order
#         request.session["cart"] = {}
#         return redirect("order_confirmation")

#     return render(request, "checkout.html", {"items": items})


# def order_confirmation(request):
#     """Confirm order placement."""
#     return render(request, "order_confirmation.html")

def about_us_view(request):
    return render(request, 'aboutUs.html')

client = MongoClient("mongodb://localhost:27017/")  # Update if remote DB
db = client["invmng"]
contact_collection = db["contact"]

def contact_us_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()

        if name and email and message:
            contact_collection.insert_one({
                'name': name,
                'email': email,
                'message': message
            })
            messages.success(request, 'Thank you for contacting us!')
            return redirect('contact_us')
        else:
            messages.error(request, 'Please fill out all fields.')

    return render(request, 'contact_us.html')