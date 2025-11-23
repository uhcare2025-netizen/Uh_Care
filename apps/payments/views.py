"""
UH Care - Payment System
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
try:
    import qrcode
except Exception:
    qrcode = None
from io import BytesIO
from django.core.files import File

from .models import Payment
from apps.appointments.models import Appointment
from django.db.models import Q


@login_required
def initiate_payment(request, appointment_id):
    """
    Initiate payment for an appointment
    """
    appointment = get_object_or_404(
        Appointment,
        id=appointment_id,
        patient=request.user
    )
    # If a payment already exists, reuse it
    payment = Payment.objects.filter(appointment=appointment, patient=request.user).first()

    if payment and payment.payment_status == 'paid':
        messages.info(request, 'This appointment has already been paid.')
        return redirect('appointments:detail', appointment_id=appointment.id)

    # GET: show a small payment choice page (online or cash-after-service)
    if request.method == 'GET':
        context = {
            'appointment': appointment,
            'payment': payment,
        }
        return render(request, 'payments/initiate.html', context)

    # POST: user selected a payment method
    method = request.POST.get('payment_method', 'online')

    if not payment:
        payment = Payment.objects.create(
            appointment=appointment,
            patient=request.user,
            amount=appointment.total_amount,
            payment_method=method,
            payment_status='unpaid'
        )
    else:
        # Do not allow changing an already-selected payment method.
        if not payment.payment_method:
            payment.payment_method = method
            payment.save()
        else:
            # Respect existing selection and inform the user
            messages.info(request, 'Payment method already selected and cannot be changed.')
            method = payment.payment_method

    if method == 'online':
        return redirect('payments:qr_code', payment_id=payment.id)

    # Cash after service selected: redirect to appointment detail and explain next steps
    messages.info(request, 'Cash after service selected. You can confirm payment once the appointment is completed.')
    return redirect('appointments:detail', appointment_id=appointment.id)


@login_required
def show_qr_code(request, payment_id):
    """
    Display QR code for payment
    """
    payment = get_object_or_404(
        Payment.objects.select_related('appointment', 'appointment__service'),
        id=payment_id,
        patient=request.user
    )
    
    if payment.payment_status == 'paid':
        messages.info(request, 'This payment has already been completed.')
        # Redirect to the most relevant detail page for this payment
        if getattr(payment, 'appointment', None):
            return redirect('appointments:detail', appointment_id=payment.appointment.id)
        if getattr(payment, 'pharmacy_order', None):
            return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)
        if getattr(payment, 'equipment_purchase', None):
            return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)
        if getattr(payment, 'equipment_rental', None):
            return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)
        return redirect('payments:history')
    
    context = {
        'payment': payment,
        'appointment': payment.appointment,
        'qr_code_url': settings.PAYMENT_QR_CODE_URL,
        'account_name': settings.PAYMENT_ACCOUNT_NAME,
        'account_number': settings.PAYMENT_ACCOUNT_NUMBER,
    }
    
    return render(request, 'payments/qr_code.html', context)


@login_required
def upload_payment_proof(request, payment_id):
    """
    Upload payment proof (screenshot)
    """
    payment = get_object_or_404(
        Payment,
        id=payment_id,
        patient=request.user
    )
    
    if payment.payment_status == 'paid':
        messages.info(request, 'This payment has already been verified.')
        # Redirect to the domain-appropriate detail page
        if getattr(payment, 'appointment', None):
            return redirect('appointments:detail', appointment_id=payment.appointment.id)
        if getattr(payment, 'pharmacy_order', None):
            return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)
        if getattr(payment, 'equipment_purchase', None):
            return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)
        if getattr(payment, 'equipment_rental', None):
            return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)
        return redirect('payments:history')
    
    if request.method == 'POST':
        transaction_id = request.POST.get('transaction_id', '')
        payment_proof = request.FILES.get('payment_proof')
        
        if not transaction_id:
            messages.error(request, 'Please provide a transaction ID.')
            return redirect('payments:upload_proof', payment_id=payment.id)
        
        # In production, upload to S3/Cloud Storage
        # For now, store the transaction ID and save uploaded file to the ImageField
        payment.transaction_id = transaction_id
        # If the payment already has a different method selected, do not overwrite it.
        if payment.payment_method and payment.payment_method != 'online':
            messages.error(request, 'Payment method for this record was previously set and cannot be changed to online.')
            return redirect('payments:detail', payment_id=payment.id)

        payment.payment_method = 'online'
        # Mark as pending verification so staff can review the uploaded proof
        payment.payment_status = 'pending'

        if payment_proof:
            # Save uploaded file to the ImageField (uses default storage)
            try:
                # Build a safe name: payment_<id>_<orig_name>
                orig_name = getattr(payment_proof, 'name', 'upload')
                filename = f"payment_{payment.id}_{orig_name}"
                payment.payment_proof_file.save(filename, File(payment_proof), save=False)
                # Keep the URL field for backward compatibility
                try:
                    payment.payment_proof_url = payment.payment_proof_file.url
                except Exception:
                    payment.payment_proof_url = ''
            except Exception:
                # Fallback: if saving to ImageField fails, attempt S3 placeholder
                payment.payment_proof_url = upload_to_s3(payment_proof)

        payment.save()

        messages.success(
            request,
            'Payment proof submitted! Our team will verify and update the status within 24 hours.'
        )

        # Redirect to the most relevant detail page for this payment:
        if getattr(payment, 'appointment', None):
            return redirect('appointments:detail', appointment_id=payment.appointment.id)
        if getattr(payment, 'pharmacy_order', None):
            return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)
        if getattr(payment, 'equipment_purchase', None):
            return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)
        if getattr(payment, 'equipment_rental', None):
            return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)

        # Fallback
        return redirect('payments:history')
    
    context = {
        'payment': payment,
    }
    
    return render(request, 'payments/upload_proof.html', context)


@login_required
def confirm_payment(request, payment_id):
    """
    Confirm cash payment after service (patient confirms they paid)
    """
    payment = get_object_or_404(
        Payment,
        id=payment_id,
        patient=request.user
    )
    
    # If already paid, send user to the relevant detail page
    if payment.payment_status == 'paid':
        messages.info(request, 'This payment has already been marked as paid.')
        if getattr(payment, 'appointment', None):
            return redirect('appointments:detail', appointment_id=payment.appointment.id)
        if getattr(payment, 'pharmacy_order', None):
            return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)
        if getattr(payment, 'equipment_purchase', None):
            return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)
        if getattr(payment, 'equipment_rental', None):
            return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)
        return redirect('payments:history')

    # Determine which domain this payment belongs to and whether it may be
    # self-confirmed by the patient (cash on delivery / after service).
    domain = None
    if getattr(payment, 'appointment', None):
        domain = 'appointment'
    elif getattr(payment, 'pharmacy_order', None):
        domain = 'pharmacy'
    elif getattr(payment, 'equipment_purchase', None):
        domain = 'equipment_purchase'
    elif getattr(payment, 'equipment_rental', None):
        domain = 'equipment_rental'

    # Validate preconditions for confirmation based on domain
    if domain == 'appointment':
        if payment.appointment.status != 'completed':
            messages.error(request, 'Payment can only be confirmed after service is completed.')
            return redirect('appointments:detail', appointment_id=payment.appointment.id)

    elif domain == 'pharmacy':
        if payment.pharmacy_order.status != 'delivered':
            messages.error(request, 'Payment can only be confirmed after the order is delivered.')
            return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)

    elif domain == 'equipment_purchase':
        if payment.equipment_purchase.status != 'delivered':
            messages.error(request, 'Payment can only be confirmed after the item is delivered.')
            return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)

    elif domain == 'equipment_rental':
        if payment.equipment_rental.status not in ('returned', 'active'):
            # Allow confirming after return or once rental is active/completed depending on your policy
            messages.error(request, 'Payment can only be confirmed once rental is delivered/returned.')
            return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)

    # Render confirmation form or handle POST
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'cash')

        # Ensure we do not change an already-selected payment method.
        if payment.payment_method and payment.payment_method != 'cash':
            messages.error(request, 'Payment method for this record was previously set and cannot be changed to cash.')
            # Redirect to the relevant detail page
            if getattr(payment, 'appointment', None):
                return redirect('appointments:detail', appointment_id=payment.appointment.id)
            if getattr(payment, 'pharmacy_order', None):
                return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)
            return redirect('payments:history')

        with transaction.atomic():
            # If method was not previously set, lock it to cash now.
            if not payment.payment_method:
                payment.payment_method = 'cash'
            payment.payment_status = 'paid'
            payment.payment_date = timezone.now()
            payment.verified_by = None  # Self-confirmed by patient
            payment.verified_at = timezone.now()
            payment.save()

            # Domain-specific side-effects
            if domain == 'appointment':
                # Update patient balance (appointments tracked in total_balance)
                profile = request.user.patient_profile
                profile.total_balance -= payment.amount
                profile.save()

            if domain == 'pharmacy':
                # Log an activity on the pharmacy order timeline
                try:
                    from apps.pharmacy.models import PharmacyOrderActivity
                    PharmacyOrderActivity.objects.create(
                        order=payment.pharmacy_order,
                        actor=request.user,
                        activity_type='payment',
                        title='Payment confirmed',
                        message='Customer confirmed cash payment on delivery.'
                    )
                except Exception:
                    # If activity model not available for any reason, ignore
                    pass

        messages.success(request, 'Payment confirmed successfully!')

        # Redirect to the appropriate detail page
        if domain == 'appointment':
            return redirect('appointments:detail', appointment_id=payment.appointment.id)
        if domain == 'pharmacy':
            return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)
        if domain == 'equipment_purchase':
            return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)
        if domain == 'equipment_rental':
            return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)

        return redirect('payments:history')

    context = {
        'payment': payment,
    }

    return render(request, 'payments/confirm_payment.html', context)


@login_required
def payment_history(request):
    """
    View payment history
    """
    payments = Payment.objects.filter(
        patient=request.user
    ).select_related(
        'appointment', 'appointment__service', 'verified_by'
    ).order_by('-created_at')
    
    # Filter by status
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        payments = payments.filter(payment_status=status_filter)
    
    # Calculate totals
    gross_total = Payment.objects.filter(
        patient=request.user
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    total_paid = Payment.objects.filter(
        patient=request.user,
        payment_status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    total_unpaid = Payment.objects.filter(
        patient=request.user,
        payment_status='unpaid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    net_unpaid = gross_total - total_paid
    
    context = {
        'payments': payments,
        'status_filter': status_filter,
        'gross_total': gross_total,
        'total_paid': total_paid,
        'net_unpaid': net_unpaid,
    }
    
    return render(request, 'payments/history.html', context)


@login_required
def qr_paid_list(request):
    """
    List all payments paid via online QR method for the current user.
    """
    payments = Payment.objects.filter(
        patient=request.user,
        payment_method='online',
        payment_status='paid'
    ).select_related('appointment', 'pharmacy_order', 'equipment_purchase', 'equipment_rental').order_by('-payment_date')

    context = {
        'payments': payments,
    }

    return render(request, 'payments/qr_paid.html', context)


@login_required
def payment_detail(request, payment_id):
    """
    Show a payment detail page for an existing Payment object.
    Allows changing/selecting payment method and proceeding to QR or cash confirmation.
    """
    payment = get_object_or_404(
        Payment.objects.select_related('appointment', 'appointment__service', 'verified_by'),
        id=payment_id,
        patient=request.user
    )

    appointment = payment.appointment

    if request.method == 'POST':
        requested = request.POST.get('payment_method', None)

        # If a method is already chosen, do not allow changing it.
        if payment.payment_method:
            messages.info(request, 'Payment method already selected and cannot be changed.')
            # Respect existing method when redirecting
            if payment.payment_method == 'online':
                return redirect('payments:qr_code', payment_id=payment.id)
            else:
                if appointment:
                    messages.info(request, 'Cash after service selected. You can confirm payment after the appointment is completed.')
                    return redirect('appointments:detail', appointment_id=appointment.id)
                if getattr(payment, 'pharmacy_order', None):
                    messages.info(request, 'Cash on delivery selected for this pharmacy order. Confirm payment once your order is delivered.')
                    return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)
                if getattr(payment, 'equipment_purchase', None):
                    messages.info(request, 'Cash on delivery selected for this purchase. Confirm payment once you receive the equipment.')
                    return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)
                if getattr(payment, 'equipment_rental', None):
                    messages.info(request, 'Cash on delivery selected for this rental. Confirm payment once rental is delivered/completed.')
                    return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)
                return redirect('payments:history')

        # No method set yet — accept the requested choice and lock it in.
        method = requested or (payment.payment_method or 'online')
        payment.payment_method = method
        payment.save()

        if method == 'online':
            return redirect('payments:qr_code', payment_id=payment.id)

        # cash selected — instruct/redirect to appointment detail
        if appointment:
            messages.info(request, 'Cash after service selected. You can confirm payment after the appointment is completed.')
            return redirect('appointments:detail', appointment_id=appointment.id)

        if getattr(payment, 'pharmacy_order', None):
            messages.info(request, 'Cash on delivery selected for this pharmacy order. Confirm payment once your order is delivered.')
            return redirect('pharmacy:order_confirmation', order_number=payment.pharmacy_order.order_number)

        if getattr(payment, 'equipment_purchase', None):
            messages.info(request, 'Cash on delivery selected for this purchase. Confirm payment once you receive the equipment.')
            return redirect('equipment:purchase_detail', order_number=payment.equipment_purchase.order_number)

        if getattr(payment, 'equipment_rental', None):
            messages.info(request, 'Cash on delivery selected for this rental. Confirm payment once rental is delivered/completed.')
            return redirect('equipment:rental_detail', rental_number=payment.equipment_rental.rental_number)

        messages.info(request, 'Cash selected. You can confirm payment after service/delivery.')
        return redirect('payments:history')

    context = {
        'payment': payment,
        'appointment': appointment,
    }

    return render(request, 'payments/detail.html', context)


@login_required
def cash_commitments(request):
    """
    Show a dedicated page listing payments where the method is 'cash' and unpaid.
    """
    qs = Payment.objects.filter(
        patient=request.user,
        payment_status='unpaid',
        payment_method='cash'
    ).select_related('pharmacy_order', 'equipment_purchase', 'equipment_rental', 'appointment').order_by('-created_at')

    # Aggregates
    cash_committed_total = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Already-paid cash payments for this user
    cash_paid_total = Payment.objects.filter(
        patient=request.user,
        payment_method='cash',
        payment_status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Overall cash-related total (paid + committed)
    cash_total = cash_paid_total + cash_committed_total

    context = {
        'payments': qs,
        'cash_committed_total': cash_committed_total,
        'cash_paid_total': cash_paid_total,
        'cash_total': cash_total,
    }

    return render(request, 'payments/cash_commitments.html', context)


# =====================================================
# ADMIN/STAFF VIEWS (Manual Payment Verification)
# =====================================================

@staff_member_required
def verify_payment(request, payment_id):
    """
    Admin manually verifies online payment
    """
    payment = get_object_or_404(Payment, id=payment_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        with transaction.atomic():
            if action == 'approve':
                payment.payment_status = 'paid'
                payment.payment_date = timezone.now()
                payment.verified_by = request.user
                payment.verified_at = timezone.now()
                payment.save()
                
                # Update patient balance
                profile = payment.patient.patient_profile
                profile.total_balance -= payment.amount
                profile.save()
                
                messages.success(request, f'Payment #{payment.id} approved.')
                
            elif action == 'reject':
                payment.notes = request.POST.get('rejection_reason', '')
                payment.save()
                
                messages.warning(request, f'Payment #{payment.id} rejected.')
        
        return redirect('admin:payments_payment_change', payment.id)
    
    context = {
        'payment': payment,
    }
    
    return render(request, 'payments/admin_verify.html', context)


# =====================================================
# UTILITY FUNCTIONS
# =====================================================

def generate_qr_code(payment):
    """
    Generate QR code for payment
    """
    # Create QR code with payment details
    qr_data = f"""
    UH Care Payment
    Amount: NPR {payment.amount}
    Payment ID: {payment.id}
    Account: {settings.PAYMENT_ACCOUNT_NUMBER}
    """
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to BytesIO
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return buffer


def upload_to_s3(file_obj):
    """
    Upload file to S3/Cloud Storage
    Placeholder - implement with boto3 in production
    """
    # TODO: Implement S3 upload
    # import boto3
    # s3_client = boto3.client('s3')
    # s3_client.upload_fileobj(file_obj, bucket, key)
    # return f"https://{bucket}.s3.amazonaws.com/{key}"
    
    return "/media/placeholder.jpg"