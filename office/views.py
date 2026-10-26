import calendar
from decimal import Decimal
from datetime import date
from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseNotAllowed
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Sum, Q
from django.utils import timezone
from .models import *
from .services import customers, role, balance, create_document, review, adjustment, update_delivery, audit
from .forms import *

def sign_in(request):
    if request.method=='POST':
        u=authenticate(request,username=request.POST.get('username'),password=request.POST.get('password'))
        if u and u.is_active:
            login(request,u); return redirect('home')
        messages.error(request,'ব্যবহারকারীর নাম অথবা পাসওয়ার্ড সঠিক নয়।')
    return render(request,'office/login.html')
@login_required
def sign_out(request):
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    logout(request); return redirect('login')

def document_scope(user):
    return Document.objects.filter(customer__in=customers(user)).select_related('customer','creator','approver')
@login_required
def home(request):
    r=role(request.user)
    if r=='delivery': return redirect('deliveries')
    cs=customers(request.user)
    es=Entry.objects.filter(customer__in=cs)
    sums=es.aggregate(debit=Sum('debit'),credit=Sum('credit'))
    metrics=[('অনুমোদিত বিক্রয়',es.filter(kind='sale').aggregate(s=Sum('debit'))['s'] or 0),('অনুমোদিত আদায়',es.filter(kind='collection').aggregate(s=Sum('credit'))['s'] or 0),('নিট বকেয়া / অগ্রিম',(sums['debit'] or 0)-(sums['credit'] or 0))]
    docs=document_scope(request.user)
    return render(request,'office/home.html',{'metrics':metrics,'pending':docs.filter(status='submitted').count(),'recent':docs.order_by('-id')[:8],'customer_count':cs.count()})
@login_required
def customer_list(request):
    q=request.GET.get('q','')
    rows=customers(request.user).filter(Q(name__icontains=q)|Q(code__icontains=q)|Q(area__icontains=q))
    if role(request.user)=='delivery': raise PermissionDenied
    return render(request,'office/customers.html',{'rows':[(c,balance(c)) for c in rows],'q':q})
@login_required
def document_list(request):
    if role(request.user)=='delivery': raise PermissionDenied
    docs=document_scope(request.user)
    status=request.GET.get('status',''); kind=request.GET.get('kind',''); q=request.GET.get('q','')
    if status: docs=docs.filter(status=status)
    if kind: docs=docs.filter(kind=kind)
    if q: docs=docs.filter(Q(customer__name__icontains=q)|Q(number__icontains=q))
    return render(request,'office/documents.html',{'docs':docs.order_by('-id')[:200]})
@login_required
def document_new(request,kind,pk=None):
    if kind not in ['sale','collection'] or role(request.user) not in ['admin','field']: raise PermissionDenied
    doc=get_object_or_404(document_scope(request.user),pk=pk) if pk else None
    if doc and (doc.creator_id!=request.user.id or doc.status not in ['draft','returned']): raise PermissionDenied
    initial={'date':timezone.localdate()}
    if doc:
        initial.update(customer=doc.customer,date=doc.date,amount=Decimal(doc.amount)/100,method=doc.method,reference=doc.reference,notes=doc.notes)
        if kind=='sale':
            l=doc.lines.order_by("id").first(); initial.update(product=l.product,quantity=l.quantity,price=Decimal(l.price)/100,discount=Decimal(l.discount)/100)
    extras=[]
    if doc and kind=='sale':
        extras=[dict(product=l.product_id,quantity=l.quantity,price=Decimal(l.price)/100,discount=Decimal(l.discount)/100) for l in doc.lines.order_by('id')[1:]]
    formset=ExtraLines(request.POST if request.method=='POST' and 'lines-TOTAL_FORMS' in request.POST else None,initial=extras,prefix='lines') if kind=='sale' else None
    form=DocumentForm(request.POST or None,user=request.user,kind=kind,initial=initial)
    if request.method=='POST' and form.is_valid() and (formset is None or not formset.is_bound or formset.is_valid()):
        try:
            if formset and formset.is_bound:
                form.cleaned_data['lines']=[form.cleaned_data.copy()]+[f.cleaned_data for f in formset if f.cleaned_data and not f.cleaned_data.get('DELETE')]
            d=create_document(request.user,form.cleaned_data['customer'],kind,form.cleaned_data['date'],form.cleaned_data,request.POST.get('action')=='submit',doc)
            messages.success(request,'সফলভাবে সংরক্ষণ করা হয়েছে।'); return redirect('document',pk=d.pk)
        except (ValidationError,IntegrityError) as e: form.add_error(None,e if isinstance(e,ValidationError) else 'Duplicate reference; use a unique transaction reference.')
    return render(request,'office/form.html',{'form':form,'title':'নতুন চালান' if kind=='sale' else 'আদায় এন্ট্রি','document_form':True,'formset':formset})
@login_required
def document_detail(request,pk):
    d=get_object_or_404(document_scope(request.user),pk=pk)
    return render(request,'office/document.html',{'d':d,'outstanding':balance(d.customer),'lines':d.lines.all()})
@login_required
def document_action(request,pk):
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    if role(request.user)!='admin': raise PermissionDenied
    try:
        action=request.POST.get('action')
        if action in ['return_credit','cancel']:
            adjustment(request.user,pk,request.POST.get('amount','0'),request.POST.get('reason',''),date.fromisoformat(request.POST['date']),action=='cancel')
        else: review(request.user,pk,action,request.POST.get('reason',''))
        messages.success(request,'সফলভাবে প্রক্রিয়া সম্পন্ন হয়েছে।')
    except (ValidationError,ValueError,KeyError) as e: messages.error(request,str(e))
    return redirect('document',pk=pk)
@login_required
def ledger(request,pk,api=False):
    c=get_object_or_404(customers(request.user),pk=pk)
    period=request.GET.get('month',timezone.localdate().strftime('%Y-%m'))
    try:
        start=date.fromisoformat(period+'-01'); end=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1])
    except ValueError: return JsonResponse({'error':'Invalid month'},status=400)
    before=Entry.objects.filter(customer=c,date__lt=start).aggregate(d=Sum('debit'),c=Sum('credit'))
    opening=(before['d'] or 0)-(before['c'] or 0); running=opening; rows=[]; sales=collections=returns=0
    for e in Entry.objects.filter(customer=c,date__range=[start,end]):
        running+=e.debit-e.credit; rows.append((e,running))
        if e.kind=='sale': sales+=e.debit
        elif e.kind=='collection': collections+=e.credit
        elif e.kind in ['return','cancellation']: returns+=e.credit
    if api: return JsonResponse({'customer':c.code,'opening_minor':opening,'closing_minor':running,'entries':[{'id':e.pk,'debit_minor':e.debit,'credit_minor':e.credit,'balance_minor':b} for e,b in rows]})
    return render(request,'office/ledger.html',locals())
@login_required
def deliveries(request):
    r=role(request.user)
    if r not in ['admin','delivery']: raise PermissionDenied
    qs=Delivery.objects.select_related('document__customer','worker')
    if r=='delivery': qs=qs.filter(worker=request.user)
    return render(request,'office/deliveries.html',{'rows':qs.order_by('-id')})
@login_required
def delivery_detail(request,pk):
    r=role(request.user); qs=Delivery.objects.select_related('document__customer','worker')
    if r=='delivery': qs=qs.filter(worker=request.user)
    elif r!='admin': raise PermissionDenied
    d=get_object_or_404(qs,pk=pk)
    if request.method=='POST':
        try:
            worker=User.objects.filter(pk=request.POST.get('worker') or None).first()
            update_delivery(request.user,pk,request.POST.get('status'),worker,request.POST.get('notes','')); messages.success(request,'ডেলিভারি আপডেট হয়েছে।'); return redirect('delivery',pk=pk)
        except ValidationError as e: messages.error(request,str(e))
    c=d.document.customer
    text=f'M. B. AGROTECH · FICTIONAL SAMPLE\n{d.document.number}\n{c.name}\n{c.address}\n{c.phone}\n'+'\n'.join(f'{l.name} / {l.package}: {l.quantity} {l.unit}' for l in d.document.lines.all())
    phone=''.join(x for x in (d.worker.profile.phone if d.worker else '') if x.isdigit())
    if phone.startswith('01'): phone='88'+phone
    share='https://wa.me/'+phone+'?'+urlencode({'text':text}) if phone else ''
    return render(request,'office/delivery.html',{'d':d,'workers':User.objects.filter(profile__role='delivery',is_active=True),'share':share,'text':text})
@login_required
def master(request,kind,pk=None):
    if kind not in ['customers','products']: raise PermissionDenied
    r=role(request.user)
    if kind=='products' and r in ['admin','field'] and request.method=='GET' and not pk and request.path=='/products/':
        return render(request,'office/products.html',{'products':Product.objects.all()})
    if r!='admin': raise PermissionDenied
    cls=CustomerForm if kind=='customers' else ProductForm
    model=Customer if kind=='customers' else Product
    obj=get_object_or_404(model,pk=pk) if pk else None
    form=cls(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=form.save(); audit(request.user,'master data saved',obj)
            opening=form.cleaned_data.get('opening_balance')
            if kind=='customers' and not pk and opening:
                amount=int(opening*100)
                Entry.objects.create(customer=obj,date=form.cleaned_data['opening_date'],kind='opening',reference='OPEN-'+obj.code,description='Opening balance',debit=max(amount,0),credit=max(-amount,0),actor=request.user)
        return redirect('customers' if kind=='customers' else 'products')
    return render(request,'office/form.html',{'form':form,'title':'মাস্টার ডেটা'})
@login_required
def users(request):
    if role(request.user)!='admin': raise PermissionDenied
    form=UserForm(request.POST or None)
    if request.method=='POST':
        if 'toggle' in request.POST:
            u=get_object_or_404(User,pk=request.POST['toggle'])
            if u==request.user: messages.error(request,'Cannot deactivate your own account')
            else:
                u.is_active=not u.is_active; u.save(); audit(request.user,'user active status changed',u)
            return redirect('users')
        if form.is_valid():
            try:
                with transaction.atomic():
                    u=User.objects.create_user(username=form.cleaned_data['username'],password=form.cleaned_data['password']); Profile.objects.create(user=u,role=form.cleaned_data['role'],phone=form.cleaned_data['phone']); audit(request.user,'user created',u)
                return redirect('users')
            except IntegrityError: form.add_error('username','Username already exists')
    return render(request,'office/users.html',{'form':form,'users':User.objects.select_related('profile').all()})
@login_required
def activity(request):
    if role(request.user)!='admin': raise PermissionDenied
    return render(request,'office/activity.html',{'rows':Audit.objects.select_related('actor').order_by('-id')[:300]})
