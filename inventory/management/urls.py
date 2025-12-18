from django.urls import path
from django.views.generic import TemplateView
from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path("workplace/register/", views.workplace_register, name="workplace_register"),
    path("workplace/login/", views.workplace_login, name="workplace_login"),
    path("get_workspaces/", views.get_workspaces, name="get_workspaces"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("add_inventory/", views.add_inventory, name="add_inventory"),
    path("add_sale/", views.add_sale, name="add_sale"),
    path("get_sales_stats/", views.get_sales_stats, name="get_sales_stats"),
    path("get_inventory_stats/", views.get_inventory_stats, name="get_inventory_stats"),
    path("get_inventory_items/", views.get_inventory_items, name="get_inventory_items"),
    path("get_items/", views.get_items, name="get_items"),
    path("get_inventory_data/", views.get_inventory_data, name="get_inventory_data"),
    path("get_sales_distribution/", views.get_sales_distribution, name="get_sales_distribution"),
    path("get_sales_data/", views.get_sales_data, name="get_sales_data"),
    path('get_inventory_predictions/', views.get_inventory_restocking_recommendations, name='get_inventory_predictions'),
    path('prediction/', views.prediction_page, name='prediction_page'),
    path('about/', views.about_us_view, name='about'),
    path('contact/', views.contact_us_view, name='contact_us'),

    # path('customer/register/', views.customer_register, name='customer_register'),
    # path('customer/login/', views.customer_login, name='customer_login'),
    # path('customer/home/', views.customer_home, name='customer_home'),
    # path('workspace/<str:workspace_name>/', views.workspace_items, name='workspace_items'),
    # path('cart/', views.view_cart, name='view_cart'),
    # path('cart/add/<str:item_id>/', views.add_to_cart, name='add_to_cart'),
    # path('checkout/', views.checkout, name='checkout'),
    # path('order/confirmation/', views.order_confirmation, name='order_confirmation'),
] 