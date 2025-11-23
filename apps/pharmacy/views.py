"""
Pharmacy app views
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction
from decimal import Decimal
from .models import Medicine, MedicineCategory, PharmacyOrder, PharmacyOrderItem
from .forms import PharmacyOrderForm
from apps.appointments.models import ServiceBooking


def medicine_list(request, category_slug=None):
    """
    Display list of medicines with filtering
    """
    medicines = Medicine.objects.filter(is_active=True, stock_quantity__gt=0).select_related('category')
    categories = MedicineCategory.objects.filter(is_active=True)
    
    # Filter by category
    selected_category = None
    if category_slug:
        selected_category = get_object_or_404(MedicineCategory, slug=category_slug, is_active=True)
        medicines = medicines.filter(category=selected_category)
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        medicines = medicines.filter(
            Q(name__icontains=search_query) |
            Q(generic_name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Filter by prescription requirement
    prescription_filter = request.GET.get('prescription', '')
    if prescription_filter:
        medicines = medicines.filter(prescription_required=prescription_filter)
    
    # Sort
    sort_by = request.GET.get('sort', 'featured')
    if sort_by == 'price_low':
        medicines = medicines.order_by('price')
    elif sort_by == 'price_high':
        medicines = medicines.order_by('-price')
    elif sort_by == 'popular':
        medicines = medicines.order_by('-total_sales')
    else:
        medicines = medicines.order_by('-is_featured', 'name')
    
    # Pagination
    paginator = Paginator(medicines, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'medicines': page_obj,
        'categories': categories,
        'selected_category': selected_category,
        'search_query': search_query,
        'sort_by': sort_by,
    }
    
    return render(request, 'pharmacy/medicine_list.html', context)


def medicine_detail(request, slug):
    """
    Display detailed information about a medicine
    """
    medicine = get_object_or_404(
        Medicine.objects.select_related('category'),
        slug=slug,
        is_active=True
    )
    
    # Related medicines
    related_medicines = Medicine.objects.filter(
        category=medicine.category,
        is_active=True,
        stock_quantity__gt=0
    ).exclude(id=medicine.id)[:4]
    
    context = {
        'medicine': medicine,
        'related_medicines': related_medicines,
    }
    
    return render(request, 'pharmacy/medicine_detail.html', context)


@login_required
def pharmacy_cart(request):
    """
    View pharmacy cart
    """
    from .models import Cart, CartItem
    
    cart, created = Cart.objects.get_or_create(
        user=request.user,
        cart_type='pharmacy'
    )
    
    cart_items = CartItem.objects.filter(
        cart=cart,
        item_type='medicine'
    ).select_related('medicine')
    
    delivery_charge = Decimal('100.00')
    total = (cart.subtotal or Decimal('0.00')) + delivery_charge

    context = {
        'cart': cart,
        'cart_items': cart_items,
        'subtotal': cart.subtotal,
        'delivery_charge': delivery_charge,  # Fixed delivery charge (Decimal)
        'total': total,
    }
    
    return render(request, 'pharmacy/cart.html', context)


@login_required
def add_to_cart(request, medicine_id):
    """
    Add medicine to cart
    """
    from .models import Cart, CartItem
    
    medicine = get_object_or_404(Medicine, id=medicine_id, is_active=True)
    
    if medicine.stock_quantity < 1:
        messages.error(request, 'This medicine is out of stock.')
        return redirect('pharmacy:detail', slug=medicine.slug)
    
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity > medicine.stock_quantity:
        messages.error(request, f'Only {medicine.stock_quantity} units available.')
        return redirect('pharmacy:detail', slug=medicine.slug)
    
    # Get or create cart
    cart, created = Cart.objects.get_or_create(
        user=request.user,
        cart_type='pharmacy'
    )
    
    # Add or update cart item
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        medicine=medicine,
        item_type='medicine',
        defaults={
            'quantity': quantity,
            'unit_price': medicine.price,
        }
    )
    
    if not created:
        cart_item.quantity += quantity
        cart_item.save()
    
    messages.success(request, f'{medicine.name} added to cart.')
    return redirect('pharmacy:cart')


@login_required
def remove_from_cart(request, item_id):
    """
    Remove item from cart
    """
    from .models import CartItem
    
    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart__user=request.user
    )
    
    cart_item.delete()
    messages.success(request, 'Item removed from cart.')
    return redirect('pharmacy:cart')


@login_required
def update_cart_quantity(request, item_id):
    """
    Update cart item quantity
    """
    from .models import CartItem
    
    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart__user=request.user
    )
    
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity <= 0:
        cart_item.delete()
        messages.success(request, 'Item removed from cart.')
    elif quantity > cart_item.medicine.stock_quantity:
        messages.error(request, f'Only {cart_item.medicine.stock_quantity} units available.')
    else:
        cart_item.quantity = quantity
        cart_item.save()
        messages.success(request, 'Cart updated.')
    
    return redirect('pharmacy:cart')


@login_required
def checkout(request):
    """
    Checkout and create pharmacy order
    """
    from .models import Cart, CartItem
    
    cart = get_object_or_404(Cart, user=request.user, cart_type='pharmacy')
    cart_items = CartItem.objects.filter(cart=cart, item_type='medicine')
    
    if not cart_items.exists():
        messages.error(request, 'Your cart is empty.')
        return redirect('pharmacy:cart')
    
    if request.method == 'POST':
        form = PharmacyOrderForm(request.POST, request.FILES)
        # Allow providers to place pharmacy orders as normal customers
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create order
                    order = form.save(commit=False)
                    order.customer = request.user
                    order.subtotal = cart.subtotal
                    order.save()
                    
                    # Create order items and update stock
                    for cart_item in cart_items:
                        PharmacyOrderItem.objects.create(
                            order=order,
                            medicine=cart_item.medicine,
                            quantity=cart_item.quantity,
                            unit_price=cart_item.unit_price,
                        )
                        
                        # Reduce stock
                        medicine = cart_item.medicine
                        medicine.stock_quantity -= cart_item.quantity
                        medicine.total_sales += cart_item.quantity
                        medicine.save()
                    
                    # Clear cart
                    cart_items.delete()
                    
                    # Create payment record linked to this pharmacy order
                    from apps.payments.models import Payment
                    # Prefill payment method from user's default payment method if present
                    from apps.payments.models import UserPaymentMethod
                    default_pm = None
                    try:
                        default_pm = UserPaymentMethod.objects.filter(user=request.user, is_default=True).first()
                    except Exception:
                        default_pm = None

                    Payment.objects.create(
                        patient=request.user,
                        amount=order.total_amount,
                        payment_status='unpaid',
                        payment_method=(default_pm.method if default_pm else None),
                        pharmacy_order=order,
                    )
                    
                    messages.success(request, f'Order #{order.order_number} placed successfully!')
                    return redirect('pharmacy:order_confirmation', order_number=order.order_number)
                    
            except Exception as e:
                messages.error(request, f'Error placing order: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Pre-fill form with user data
        initial = {
            'delivery_address': getattr(request.user, 'address', ''),
            'delivery_phone': getattr(request.user, 'phone_number', ''),
        }
        form = PharmacyOrderForm(initial=initial)
        # Providers are allowed to use the checkout form as customers
    
    delivery_charge = Decimal('100.00')
    total = (cart.subtotal or Decimal('0.00')) + delivery_charge

    context = {
        'form': form,
        'cart_items': cart_items,
        'subtotal': cart.subtotal,
        'delivery_charge': delivery_charge,
        'total': total,
    }
    
    return render(request, 'pharmacy/checkout.html', context)


@login_required
def order_confirmation(request, order_number):
    """
    Order confirmation page
    """
    order = get_object_or_404(
        PharmacyOrder.objects.prefetch_related('items__medicine'),
        order_number=order_number,
        customer=request.user
    )
    
    # Build recent activities timeline using available timestamps
    from apps.payments.models import Payment
    activities = []

    # Order placed
    activities.append({
        'title': 'Order placed',
        'message': 'Your order was placed successfully.',
        'time': order.created_at,
        'status': 'placed',
    })

    # Payment record (if any)
    payment = Payment.objects.filter(pharmacy_order=order).order_by('created_at').first()
    if payment:
        activities.append({
            'title': 'Payment record',
            'message': f'Payment record created (Method: {payment.get_payment_method_display() or payment.payment_method}).',
            'time': payment.created_at,
            'status': 'payment',
        })

    # Prescription uploaded/verified
    if order.prescription_image:
        activities.append({
            'title': 'Prescription uploaded',
            'message': 'Prescription was uploaded for verification.',
            'time': order.created_at,
            'status': 'prescription',
        })
    if order.prescription_verified:
        activities.append({
            'title': 'Prescription verified',
            'message': 'Prescription has been verified by our team.',
            'time': order.updated_at,
            'status': 'prescription_verified',
        })

    # Status milestone
    if order.status and order.status != 'pending':
        activities.append({
            'title': f'Order {order.get_status_display()}',
            'message': f'Order status updated to {order.get_status_display()}.',
            'time': order.updated_at,
            'status': order.status,
        })

    # Delivered
    if order.delivered_at:
        activities.append({
            'title': 'Order delivered',
            'message': 'Order has been delivered to the provided address.',
            'time': order.delivered_at,
            'status': 'delivered',
        })

    # Sort activities by time ascending
    activities = sorted([a for a in activities if a.get('time')], key=lambda x: x['time'])

    context = {
        'order': order,
        'activities': activities,
    }
    
    return render(request, 'pharmacy/order_confirmation.html', context)


@login_required
def my_orders(request):
    """
    View user's pharmacy orders
    """
    orders = (
        PharmacyOrder.objects.filter(customer=request.user)
        .prefetch_related('items__medicine', 'payments')
        .order_by('-created_at')
    )

    # Attach any unpaid payment to the order for simple template rendering
    for o in orders:
        unpaid = None
        for pay in o.payments.all():
            if getattr(pay, 'payment_status', None) == 'unpaid':
                unpaid = pay
                break
        o.unpaid_payment = unpaid

    context = {
        'orders': orders,
    }

    return render(request, 'pharmacy/my_orders.html', context)



@login_required
def cancel_order(request, order_number):
    """Allow a customer (or staff) to cancel a pending pharmacy order via POST.

    Cancelling will set order.status = 'cancelled', restore medicine stock
    for each item, and annotate linked payments as refunded when appropriate.
    """
    order = get_object_or_404(PharmacyOrder, order_number=order_number)

    # permission check
    if order.customer != request.user and not request.user.is_staff:
        messages.error(request, 'You are not allowed to cancel this order.')
        return redirect('pharmacy:my_orders')

    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('pharmacy:order_confirmation', order_number=order.order_number)

    if order.status != 'pending':
        messages.error(request, 'Only pending orders can be cancelled.')
        return redirect('pharmacy:order_confirmation', order_number=order.order_number)

    try:
        # mark cancelled and save cancellation time
        order.status = 'cancelled'
        order.cancellation_reason = request.POST.get('cancellation_reason', '')
        order.save()

        # restore stock for each item
        for item in order.items.select_related('medicine'):
            med = item.medicine
            med.stock_quantity = getattr(med, 'stock_quantity', 0) + item.quantity
            med.save()

        # mark linked payments as refunded where applicable
        from apps.payments.models import Payment
        for pay in order.payments.all():
            if pay.payment_status not in ('refunded', 'paid'):
                pay.payment_status = 'refunded'
                pay.notes = (pay.notes or '') + f"\nAuto-refunded on order cancel by user {request.user.id}"
                pay.verified_at = timezone.now()
                pay.save()

        messages.success(request, f'Order {order.order_number} has been cancelled.')
    except Exception as e:
        messages.error(request, f'Could not cancel order: {e}')

    return redirect('pharmacy:my_orders')



@login_required
def provider_schedule(request):
    """
    Provider's schedule view - calendar of all appointments
    """
    if request.user.role != 'provider':
        return redirect('dashboard:home')
    
    user = request.user
    
    # Get month and year from query params
    current_date = timezone.now()
    month = int(request.GET.get('month', current_date.month))
    year = int(request.GET.get('year', current_date.year))
    
    # Get marketplace service bookings for the selected month
    appointments = ServiceBooking.objects.filter(
        provider=user,
        appointment_date__year=year,
        appointment_date__month=month
    ).select_related('service', 'patient').order_by('appointment_date', 'appointment_time')
    
    context = {
        'appointments': appointments,
        'current_month': month,
        'current_year': year,
    }
    
    return render(request, 'dashboard/provider_schedule.html', context)


@login_required
def admin_dashboard(request):
    """
    Admin dashboard with system-wide statistics
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect('dashboard:home')
    
    today = timezone.now().date()
    this_month_start = today.replace(day=1)
    last_30_days = today - timedelta(days=30)
    
    # User statistics
    total_users = User.objects.count()
    total_patients = User.objects.filter(role='patient').count()
    total_providers = User.objects.filter(role='provider', is_active=True).count()
    pending_providers = User.objects.filter(role='provider', is_active=False).count()
    
    # Marketplace booking statistics
    total_appointments = ServiceBooking.objects.count()
    this_month_appointments = ServiceBooking.objects.filter(
        created_at__gte=this_month_start
    ).count()
    
    pending_appointments = ServiceBooking.objects.filter(status='pending').count()
    completed_appointments = ServiceBooking.objects.filter(status='completed').count()
    
    # Financial statistics
    total_revenue = Payment.objects.filter(
        payment_status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    this_month_revenue = Payment.objects.filter(
        payment_status='paid',
        payment_date__gte=this_month_start
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    pending_payments_total = Payment.objects.filter(
        payment_status='unpaid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Service statistics
    total_services = Service.objects.filter(is_active=True).count()
    most_booked_services = Service.objects.filter(
        is_active=True
    ).order_by('-total_bookings')[:5]
    
    # Recent marketplace bookings/activity
    recent_appointments = ServiceBooking.objects.select_related(
        'patient', 'provider', 'service'
    ).order_by('-created_at')[:10]
    
    recent_payments = Payment.objects.select_related(
        'patient', 'appointment', 'service_booking'
    ).order_by('-created_at')[:10]
    
    stats = {
        'total_users': total_users,
        'total_patients': total_patients,
        'total_providers': total_providers,
        'pending_providers': pending_providers,
        'total_appointments': total_appointments,
        'this_month_appointments': this_month_appointments,
        'pending_appointments': pending_appointments,
        'completed_appointments': completed_appointments,
        'total_revenue': total_revenue,
        'this_month_revenue': this_month_revenue,
        'pending_payments_total': pending_payments_total,
        'total_services': total_services,
    }
    
    context = {
        # Provide both machine-friendly stats and aliases expected by templates
        'stats': stats,
        'most_booked_services': most_booked_services,
        'recent_appointments': recent_appointments,
        'recent_payments': recent_payments,
        'recent_activity': [
            f"Appointment: {a.patient.get_full_name()} booked {a.service.name} on {a.appointment_date.strftime('%Y-%m-%d')}" for a in recent_appointments
        ] + [
            f"Payment: {p.patient.get_full_name()} - रू {p.amount} ({p.get_payment_status_display() if hasattr(p, 'get_payment_status_display') else p.payment_status})" for p in recent_payments
        ],
        # Aliases expected by admin template
        'stats': {
            **stats,
            'users_count': total_users,
            'services_count': total_services,
            'pending_payments_total': pending_payments_total,
        },
    }
    
    return render(request, 'dashboard/admin_dashboard.html', context)