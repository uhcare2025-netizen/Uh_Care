from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction
from .models import Equipment, EquipmentCategory
from .forms import EquipmentRentalForm, EquipmentPurchaseForm
from django.utils import timezone



def equipment_list(request, category_slug=None):
    """
    Display list of equipment
    """
    # use available_units field (models define available_units)
    equipment = Equipment.objects.filter(is_active=True, available_units__gt=0).select_related('category')
    categories = EquipmentCategory.objects.filter()
    
    # Filter by category
    selected_category = None
    if category_slug:
        selected_category = get_object_or_404(EquipmentCategory, slug=category_slug)
        equipment = equipment.filter(category=selected_category)
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        equipment = equipment.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Sort
    sort_by = request.GET.get('sort', 'featured')
    if sort_by == 'price_low':
        equipment = equipment.order_by('price_per_day')
    elif sort_by == 'price_high':
        equipment = equipment.order_by('-price_per_day')
    else:
        equipment = equipment.order_by('name')
    
    # Pagination
    paginator = Paginator(equipment, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'equipment': page_obj,
        'categories': categories,
        'selected_category': selected_category,
        'search_query': search_query,
        'sort_by': sort_by,
    }
    
    return render(request, 'equipment/equipment_list.html', context)


def equipment_detail(request, slug):
    """
    Display detailed information about equipment
    """
    equipment = get_object_or_404(
        Equipment.objects.select_related('category'),
        slug=slug,
        is_active=True
    )
    
    # Related equipment
    related_equipment = Equipment.objects.filter(
        category=equipment.category,
        is_active=True,
        available_units__gt=0
    ).exclude(id=equipment.id)[:4]
    
    context = {
        'equipment': equipment,
        'related_equipment': related_equipment,
    }
    
    return render(request, 'equipment/equipment_detail.html', context)


@login_required
def rent_equipment(request, equipment_id):
    """
    Rent equipment
    """
    equipment = get_object_or_404(Equipment, id=equipment_id, is_active=True)
    
    # Allow providers to rent equipment as normal users (they act as the customer)

    # treat stock/availability using available_units
    if equipment.available_units < 1:
        messages.error(request, 'This equipment is currently unavailable.')
        return redirect('equipment:detail', slug=equipment.slug)
    
    if request.method == 'POST':
        form = EquipmentRentalForm(request.POST, equipment=equipment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    rental = form.save(commit=False)
                    rental.customer = request.user
                    rental.equipment = equipment
                    rental.save()
                    
                    # Reduce available units (never go below 0)
                    equipment.available_units = max(0, equipment.available_units - rental.quantity)
                    equipment.save()
                    
                    # Create payment record linked to this equipment rental
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
                        amount=rental.total_amount,
                        payment_status='unpaid',
                        payment_method=(default_pm.method if default_pm else None),
                        equipment_rental=rental,
                    )
                    
                    messages.success(request, f'Equipment rental confirmed!')
                    return redirect('equipment:my_rentals')
            except Exception as e:
                messages.error(request, f'Error processing rental: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        initial = {
            'delivery_address': getattr(request.user, 'address', ''),
            'delivery_phone': getattr(request.user, 'phone_number', ''),
        }
        form = EquipmentRentalForm(initial=initial, equipment=equipment)
    
    context = {
        'form': form,
        'equipment': equipment,
    }
    
    return render(request, 'equipment/rent_equipment.html', context)


@login_required
def buy_equipment(request, equipment_id):
    """
    Buy equipment
    """
    equipment = get_object_or_404(Equipment, id=equipment_id, is_active=True)
    
    # Allow providers to purchase equipment as normal users (they act as the customer)

    if equipment.available_units < 1:
        messages.error(request, 'This equipment is currently unavailable.')
        return redirect('equipment:detail', slug=equipment.slug)
    
    if request.method == 'POST':
        form = EquipmentPurchaseForm(request.POST, equipment=equipment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    purchase = form.save(commit=False)
                    purchase.customer = request.user
                    purchase.equipment = equipment
                    purchase.unit_price = equipment.purchase_price
                    purchase.save()
                    
                    # Reduce available units (never go below 0)
                    equipment.available_units = max(0, equipment.available_units - purchase.quantity)
                    equipment.save()
                    
                    # Create payment record linked to this equipment purchase
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
                        amount=purchase.total_amount,
                        payment_status='unpaid',
                        payment_method=(default_pm.method if default_pm else None),
                        equipment_purchase=purchase,
                    )
                    
                    messages.success(request, f'Purchase order placed successfully!')
                    return redirect('equipment:my_purchases')
            except Exception as e:
                messages.error(request, f'Error processing purchase: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        initial = {
            'delivery_address': getattr(request.user, 'address', ''),
            'delivery_phone': getattr(request.user, 'phone_number', ''),
        }
        form = EquipmentPurchaseForm(initial=initial, equipment=equipment)
    
    context = {
        'form': form,
        'equipment': equipment,
    }
    
    return render(request, 'equipment/buy_equipment.html', context)


@login_required
def my_rentals(request):
    """
    View user's equipment rentals
    """
    from .models import EquipmentRental
    # Return actual rentals for the logged-in user
    rentals = EquipmentRental.objects.filter(customer=request.user).select_related('equipment').order_by('-created_at')

    context = {
        'rentals': rentals,
    }

    return render(request, 'equipment/my_rentals.html', context)


@login_required
def my_purchases(request):
    """
    View user's equipment purchases
    """
    from .models import EquipmentPurchase
    # Prefetch related payments so we can surface an unpaid payment (if any)
    purchases = (
        EquipmentPurchase.objects.filter(customer=request.user)
        .select_related('equipment')
        .prefetch_related('payments')
        .order_by('-created_at')
    )

    # Attach the first unpaid payment (if present) to each purchase to keep
    # template logic simple and avoid extra DB queries in the template.
    for p in purchases:
        unpaid = None
        # payments is prefetched, this iterates the cached queryset
        for pay in p.payments.all():
            if getattr(pay, 'payment_status', None) == 'unpaid':
                unpaid = pay
                break
        p.unpaid_payment = unpaid

    context = {
        'purchases': purchases,
    }

    return render(request, 'equipment/my_purchases.html', context)


@login_required
def purchase_detail(request, order_number):
    """Show details for a single purchase order (only owner or staff)."""
    from .models import EquipmentPurchase
    # Ensure the user owns this order unless staff
    order = get_object_or_404(EquipmentPurchase, order_number=order_number)
    if order.customer != request.user and not request.user.is_staff:
        return redirect('equipment:my_purchases')

    context = {
        'purchase': order,
    }
    return render(request, 'equipment/purchase_detail.html', context)


@login_required
def cancel_purchase(request, order_number):
    """Allow customer (or staff) to cancel a pending purchase via POST.

    Cancelling will set the purchase `status` to 'cancelled', restore inventory
    for the associated equipment, and annotate any linked payments as refunded.
    Only pending purchases can be cancelled.
    """
    from .models import EquipmentPurchase
    from apps.payments.models import Payment

    purchase = get_object_or_404(EquipmentPurchase, order_number=order_number)
    # permission: owner or staff
    if purchase.customer != request.user and not request.user.is_staff:
        messages.error(request, 'You are not allowed to cancel this purchase.')
        return redirect('equipment:my_purchases')

    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('equipment:purchase_detail', order_number=purchase.order_number)

    if purchase.status != 'pending':
        messages.error(request, 'Only pending purchases can be cancelled.')
        return redirect('equipment:purchase_detail', order_number=purchase.order_number)

    try:
        # mark cancelled
        purchase.status = 'cancelled'
        purchase.save()

        # restore inventory
        equipment = purchase.equipment
        equipment.available_units = getattr(equipment, 'available_units', 0) + purchase.quantity
        equipment.save()

        # Annotate any linked payments: mark refunded if not already refunded/paid
        for pay in purchase.payments.all():
            if pay.payment_status != 'refunded' and pay.payment_status != 'paid':
                pay.payment_status = 'refunded'
                pay.notes = (pay.notes or '') + f"\nAuto-refunded on purchase cancel {request.user.id}"
                pay.verified_at = timezone.now()
                pay.save()

        messages.success(request, f'Purchase {purchase.order_number} has been cancelled.')
    except Exception as e:
        messages.error(request, f'Could not cancel purchase: {e}')

    return redirect('equipment:my_purchases')


@login_required
def rental_detail(request, rental_number):
    """Show details for a single rental (only owner or staff)."""
    from .models import EquipmentRental
    rental = get_object_or_404(EquipmentRental, rental_number=rental_number)
    if rental.customer != request.user and not request.user.is_staff:
        return redirect('equipment:my_rentals')

    context = {
        'rental': rental,
    }
    return render(request, 'equipment/rental_detail.html', context)


@login_required
def cancel_rental(request, rental_number):
    """Allow customer (or staff) to cancel a pending rental."""
    from .models import EquipmentRental

    rental = get_object_or_404(EquipmentRental, rental_number=rental_number)
    # permission: owner or staff
    if rental.customer != request.user and not request.user.is_staff:
        messages.error(request, 'You are not allowed to cancel this rental.')
        return redirect('equipment:my_rentals')

    if request.method != 'POST':
        # For safety, only allow POST to cancel
        messages.error(request, 'Invalid request method.')
        return redirect('equipment:rental_detail', rental_number=rental.rental_number)

    if rental.status != 'pending':
        messages.error(request, 'Only pending rentals can be cancelled.')
        return redirect('equipment:rental_detail', rental_number=rental.rental_number)

    # perform cancellation
    try:
        rental.status = 'cancelled'
        rental.cancelled_at = timezone.now()
        rental.save()

        # return units to inventory
        equipment = rental.equipment
        equipment.available_units = getattr(equipment, 'available_units', 0) + rental.quantity
        equipment.save()

        messages.success(request, f'Rental {rental.rental_number} has been cancelled.')
    except Exception as e:
        messages.error(request, f'Could not cancel rental: {e}')

    return redirect('equipment:my_rentals')


@login_required
def return_rental(request, rental_number):
    """Mark a rental as returned. Only provider/staff or the customer when returning can mark returned.

    This view accepts POST only to avoid accidental GET-triggered state changes.
    """
    from .models import EquipmentRental

    rental = get_object_or_404(EquipmentRental, rental_number=rental_number)
    if rental.customer != request.user and not request.user.is_staff:
        messages.error(request, 'You are not allowed to mark this rental returned.')
        return redirect('equipment:my_rentals')

    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('equipment:rental_detail', rental_number=rental.rental_number)

    if rental.status not in ('active', 'confirmed'):
        messages.error(request, 'Only active or confirmed rentals can be marked returned.')
        return redirect('equipment:rental_detail', rental_number=rental.rental_number)

    try:
        rental.status = 'returned'
        rental.actual_return_date = timezone.now().date()
        rental.save()

        # restore inventory
        equipment = rental.equipment
        equipment.available_units = getattr(equipment, 'available_units', 0) + rental.quantity
        equipment.save()

        messages.success(request, f'Rental {rental.rental_number} marked as returned.')
    except Exception as e:
        messages.error(request, f'Could not mark returned: {e}')

    return redirect('equipment:my_rentals')
