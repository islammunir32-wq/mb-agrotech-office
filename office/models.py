from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q, F

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=12, choices=[('admin','Administrator'),('field','Field staff'),('delivery','Delivery staff')])
    phone = models.CharField(max_length=24, blank=True)

class Customer(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=160)
    contact = models.CharField(max_length=120)
    phone = models.CharField(max_length=24)
    address = models.TextField()
    area = models.CharField(max_length=100)
    assigned = models.ForeignKey(User, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    def __str__(self): return f'{self.code} · {self.name}'

class Product(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    package = models.CharField(max_length=80)
    unit = models.CharField(max_length=30)
    price = models.PositiveBigIntegerField(help_text='BDT minor units (paisa)')
    active = models.BooleanField(default=True)
    def __str__(self): return f'{self.name} · {self.package} (fictional sample)'

class Document(models.Model):
    KINDS = [('sale','Invoice'),('collection','Collection')]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    creator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='documents')
    kind = models.CharField(max_length=12, choices=KINDS)
    status = models.CharField(max_length=12, default='draft')
    date = models.DateField()
    amount = models.PositiveBigIntegerField(default=0)
    number = models.CharField(max_length=40, unique=True, null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    method = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    approver = models.ForeignKey(User, null=True, on_delete=models.PROTECT, related_name='approved_documents')
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0),name='positive_document_amount'), models.UniqueConstraint(fields=['reference'], condition=Q(kind='collection') & ~Q(reference=''), name='unique_collection_reference')]

class Line(models.Model):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    package = models.CharField(max_length=80)
    unit = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField()
    price = models.PositiveBigIntegerField()
    discount = models.PositiveBigIntegerField(default=0)
    total = models.PositiveBigIntegerField()
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0) & Q(total__gt=0) & Q(discount__lte=F('quantity')*F('price')) & Q(total=F('quantity')*F('price')-F('discount')),name='valid_line_arithmetic')]

class Entry(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    document = models.ForeignKey(Document, null=True, on_delete=models.PROTECT)
    date = models.DateField()
    kind = models.CharField(max_length=20)
    reference = models.CharField(max_length=80)
    description = models.TextField()
    debit = models.PositiveBigIntegerField(default=0)
    credit = models.PositiveBigIntegerField(default=0)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['date','id']
        constraints = [models.CheckConstraint(condition=(Q(debit__gt=0,credit=0)|Q(credit__gt=0,debit=0)),name='single_positive_ledger_side'), models.UniqueConstraint(fields=['customer'],condition=Q(kind='opening'),name='one_opening_per_customer'), models.UniqueConstraint(fields=['document','kind'], condition=Q(kind__in=['sale','collection','cancellation']), name='one_post_per_document_kind')]

class Delivery(models.Model):
    document = models.OneToOneField(Document, on_delete=models.PROTECT)
    worker = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, default='pending')
    notes = models.TextField(blank=True)

class Audit(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=100)
    reason = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
