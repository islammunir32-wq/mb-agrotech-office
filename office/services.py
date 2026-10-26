from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Sum
from .models import *

def role(user):
    if not user.is_active: raise PermissionDenied
    try: return user.profile.role
    except Profile.DoesNotExist: raise PermissionDenied

def customers(user):
    r = role(user)
    if r == 'admin': return Customer.objects.all()
    if r == 'field': return Customer.objects.filter(assigned=user)
    return Customer.objects.none()

def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > Decimal('10000000000') or n != n.quantize(Decimal('.01')): raise ValueError
        return int(n * 100)
    except (InvalidOperation, ValueError): raise ValidationError('সঠিক টাকা লিখুন (সর্বোচ্চ ২ দশমিক)।')

def balance(customer):
    a = Entry.objects.filter(customer=customer).aggregate(d=Sum('debit'),c=Sum('credit'))
    return (a['d'] or 0)-(a['c'] or 0)

def audit(user, action, obj, reason=''):
    Audit.objects.create(actor=user,action=action,target=f'{obj.__class__.__name__}:{obj.pk}',reason=reason)

@transaction.atomic
def create_document(user, customer, kind, date, data, submit=False, existing=None):
    if role(user) not in ['admin','field'] or not customers(user).filter(pk=customer.pk,active=True).exists(): raise PermissionDenied
    if kind not in ['sale','collection']: raise ValidationError('Invalid document kind')
    doc = existing
    if doc:
        doc = Document.objects.select_for_update().get(pk=doc.pk)
        if doc.creator_id != user.id or doc.status not in ['draft','returned']: raise PermissionDenied
        if doc.customer_id != customer.id or doc.kind != kind: raise ValidationError('Customer and document type cannot change')
        doc.lines.all().delete()
    else: doc = Document(customer=customer,creator=user,kind=kind)
    doc.date=date; doc.notes=data.get('notes',''); doc.reference=data.get('reference','').strip(); doc.method=data.get('method','')
    doc.status='submitted' if submit else 'draft'; doc.reason=''
    if kind == 'sale':
        line_data=data.get('lines') or [data]
        if not 1 <= len(line_data) <= 20: raise ValidationError('Use between 1 and 20 invoice lines')
        snapshots=[]
        for item in line_data:
            product=Product.objects.get(pk=getattr(item['product'], 'pk', item['product']),active=True)
            try: qty=int(item['quantity'])
            except (ValueError,TypeError): raise ValidationError('পূর্ণ সংখ্যায় পরিমাণ লিখুন।')
            if qty <= 0 or qty > 100000: raise ValidationError('Invalid quantity')
            price=money(item['price']); discount=money(item.get('discount','0'))
            if discount > qty*price: raise ValidationError('Discount exceeds line value')
            total=qty*price-discount
            if total<=0: raise ValidationError('Invoice lines must have positive totals')
            snapshots.append(dict(product=product,name=product.name,package=product.package,unit=product.unit,quantity=qty,price=price,discount=discount,total=total))
        doc.amount=sum(l['total'] for l in snapshots)
        doc.save()
        for snapshot in snapshots: Line.objects.create(document=doc,**snapshot)
    else:
        doc.amount=money(data['amount'])
        if doc.amount<=0 or doc.method not in ['cash','bank','mobile'] or not doc.reference: raise ValidationError('Amount, payment method and unique reference are required')
        if Document.objects.filter(kind='collection',reference=doc.reference).exclude(pk=doc.pk).exists(): raise ValidationError('এই লেনদেনের রেফারেন্স ইতিমধ্যে আছে।')
        doc.save()
    audit(user,'submitted' if submit else 'draft saved',doc)
    return doc

@transaction.atomic
def review(user, pk, action, reason=''):
    if role(user) != 'admin': raise PermissionDenied
    doc=Document.objects.select_for_update().get(pk=pk)
    if action == 'approve' and doc.status == 'approved': return doc
    if doc.status != 'submitted': raise ValidationError('Only submitted documents can be reviewed')
    if action not in ['approve','return','reject']: raise ValidationError('Invalid review')
    if action != 'approve' and not reason.strip(): raise ValidationError('কারণ লিখুন।')
    if action == 'approve':
        if doc.kind=='sale' and sum(doc.lines.values_list('total',flat=True)) != doc.amount: raise ValidationError('Inconsistent invoice total')
        doc.status='approved'; doc.approver=user
        doc.number=f'{"INV" if doc.kind=="sale" else "RCPT"}-{doc.date.year}-{doc.pk:06d}'
        Entry.objects.create(customer=doc.customer,document=doc,date=doc.date,kind=doc.kind,reference=doc.number,description=doc.get_kind_display(),debit=doc.amount if doc.kind=='sale' else 0,credit=doc.amount if doc.kind=='collection' else 0,actor=user)
        if doc.kind=='sale': Delivery.objects.create(document=doc)
    else: doc.status='returned' if action=='return' else 'rejected'; doc.reason=reason
    doc.save(); audit(user,action,doc,reason)
    return doc

@transaction.atomic
def adjustment(user,pk,amount,reason,date,cancel=False):
    if role(user)!='admin': raise PermissionDenied
    doc=Document.objects.select_for_update().get(pk=pk)
    if doc.kind!='sale' or doc.status!='approved' or not reason.strip(): raise ValidationError('Approved sale and reason required')
    prior=Entry.objects.filter(document=doc,kind__in=['return','cancellation']).aggregate(s=Sum('credit'))['s'] or 0
    amount=doc.amount-prior if cancel else money(amount)
    if amount<=0 or amount+prior>doc.amount: raise ValidationError('Adjustment exceeds remaining approved amount')
    if date<doc.date: raise ValidationError('Adjustment date cannot precede the invoice')
    e=Entry.objects.create(customer=doc.customer,document=doc,date=date,kind='cancellation' if cancel else 'return',reference=f'ADJ-{doc.pk}-{prior+amount}',description=reason,credit=amount,actor=user)
    audit(user,'cancellation' if cancel else 'return',e,reason)
    return e

@transaction.atomic
def update_delivery(user,pk,status,worker=None,notes=''):
    r=role(user)
    qs=Delivery.objects.select_for_update()
    if r=='delivery': qs=qs.filter(worker=user)
    elif r!='admin': raise PermissionDenied
    try: d=qs.get(pk=pk)
    except Delivery.DoesNotExist: raise PermissionDenied
    if status=='assigned' and r=='admin':
        if not worker or not worker.is_active or role(worker)!='delivery': raise ValidationError('Active delivery worker required')
        if d.status in ['delivered','failed']: raise ValidationError('Delivery is complete')
        d.worker=worker
    elif status in ['delivered','failed'] and d.status=='assigned':
        if status=='failed' and not notes.strip(): raise ValidationError('Failure reason required')
    else: raise ValidationError('Invalid delivery transition')
    d.status=status; d.notes=notes; d.save(); audit(user,status,d,notes)
    return d
