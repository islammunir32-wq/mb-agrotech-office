from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from .models import *
from .services import *

class AccountingTests(TestCase):
    def setUp(self):
        self.admin=self.user('admin','admin'); self.a=self.user('a','field'); self.b=self.user('b','field'); self.da=self.user('da','delivery'); self.db=self.user('db','delivery')
        self.ca=Customer.objects.create(code='A',name='বাংলা নমুনা',contact='Sample',phone='',address='Sample',area='Sample',assigned=self.a)
        self.cb=Customer.objects.create(code='B',name='Other',contact='Sample',phone='',address='Sample',area='Sample',assigned=self.b)
        self.p=Product.objects.create(code='P',name='নমুনা পণ্য',package='Fictional pack',unit='pack',price=100000)
    def user(self,name,r):
        u=User.objects.create_user(username=name,password='test-only-password-532!'); Profile.objects.create(user=u,role=r); return u
    def sale(self,customer=None,submit=True):
        return create_document(self.a,customer or self.ca,'sale',date(2026,10,5),{'product':self.p,'quantity':5,'price':'1000','discount':'0'},submit)
    def collection(self,amount='3000',reference='REF'):
        return create_document(self.a,self.ca,'collection',date(2026,10,7),{'amount':amount,'method':'cash','reference':reference},True)
    def test_staff_scope_direct_urls_api_search_reports(self):
        self.client.force_login(self.a)
        for path in [f'/customers/{self.cb.pk}/ledger/',f'/api/customers/{self.cb.pk}/ledger/']:
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.get(f'/customers/{self.ca.pk}/ledger/').status_code,200)
        self.assertEqual(self.client.get(f'/api/customers/{self.ca.pk}/ledger/').status_code,200)
        self.assertEqual(self.client.get('/customers/?q=Other').context['rows'],[])
        with self.assertRaises(PermissionDenied): self.sale(self.cb)
        d=create_document(self.b,self.cb,'sale',date(2026,10,5),{'product':self.p,'quantity':1,'price':'1000','discount':'0'},True)
        self.assertEqual(self.client.get(f'/documents/{d.pk}/').status_code,404)
        self.assertEqual(self.client.post(f'/documents/{d.pk}/action/',{'action':'approve'}).status_code,403)
    def test_draft_and_pending_no_balance_effect(self):
        self.sale(submit=False); self.sale(); self.assertEqual(balance(self.ca),0)
    def test_approval_exactly_once_and_final_number(self):
        d=self.sale(); review(self.admin,d.pk,'approve'); review(self.admin,d.pk,'approve')
        d.refresh_from_db(); self.assertEqual(d.status,'approved'); self.assertTrue(d.number.startswith('INV-2026-')); self.assertEqual(balance(self.ca),500000)
        self.assertEqual(Entry.objects.filter(document=d).count(),1); self.assertEqual(Delivery.objects.filter(document=d).count(),1)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Entry.objects.create(customer=self.ca,document=d,date=d.date,kind='sale',reference='duplicate',actor=self.admin)
    def test_collection_pending_approved_and_advance(self):
        c=self.collection(); self.assertEqual(balance(self.ca),0)
        review(self.admin,c.pk,'approve'); review(self.admin,c.pk,'approve'); self.assertEqual(balance(self.ca),-300000)
        self.assertEqual(Entry.objects.filter(document=c).count(),1)
    def test_duplicate_reference(self):
        self.collection()
        with self.assertRaises(ValidationError): self.collection()
    def test_returns_cancellation_preserve_original_and_cap(self):
        d=self.sale(); review(self.admin,d.pk,'approve')
        adjustment(self.admin,d.pk,'500','Return',date(2026,10,6))
        with self.assertRaises(ValidationError): adjustment(self.admin,d.pk,'4501','Excess',date(2026,10,7))
        adjustment(self.admin,d.pk,'0','Cancel remainder',date(2026,10,7),True)
        self.assertEqual(balance(self.ca),0); self.assertEqual(Entry.objects.get(document=d,kind='sale').debit,500000)
        d.refresh_from_db(); self.assertEqual(d.amount,500000); self.assertEqual(d.status,'approved')
        with self.assertRaises(ValidationError): adjustment(self.admin,d.pk,'1','Excess',date(2026,10,8))
        self.assertEqual(Audit.objects.filter(action='cancellation').count(),1)
    def test_monthly_reconciliation_example(self):
        Entry.objects.create(customer=self.ca,date=date(2026,9,1),kind='opening',reference='OPEN',description='Opening',debit=1000000,actor=self.admin)
        d=self.sale(); review(self.admin,d.pk,'approve'); adjustment(self.admin,d.pk,'500','Return',date(2026,10,6)); c=self.collection(); review(self.admin,c.pk,'approve')
        self.client.force_login(self.a)
        r=self.client.get(f'/api/customers/{self.ca.pk}/ledger/?month=2026-10').json()
        self.assertEqual(r['opening_minor'],1000000); self.assertEqual(r['closing_minor'],1150000)
        self.assertEqual(self.client.get(f'/api/customers/{self.ca.pk}/ledger/?month=2026-11').json()['opening_minor'],1150000)
    def test_delivery_scope_and_failure_no_reversal(self):
        d=self.sale(); review(self.admin,d.pk,'approve'); delivery=d.delivery
        update_delivery(self.admin,delivery.pk,'assigned',self.da)
        self.client.force_login(self.db)
        self.assertEqual(self.client.get(f'/deliveries/{delivery.pk}/').status_code,404)
        self.assertEqual(self.client.post(f'/deliveries/{delivery.pk}/',{'status':'delivered'}).status_code,404)
        self.client.force_login(self.da)
        self.assertContains(self.client.get(f'/deliveries/{delivery.pk}/'),'ডেলিভারি কপি')
        for p in [f'/customers/{self.ca.pk}/ledger/',f'/api/customers/{self.ca.pk}/ledger/',f'/documents/{d.pk}/','/customers/','/products/']:
            self.assertIn(self.client.get(p).status_code,[403,404])
        update_delivery(self.da,delivery.pk,'failed',notes='Could not reach sample address'); self.assertEqual(balance(self.ca),500000)
    def test_price_snapshot_and_approved_edit_block(self):
        d=self.sale(); review(self.admin,d.pk,'approve'); self.p.price=999999; self.p.name='Changed'; self.p.save()
        self.assertEqual(d.lines.get().price,100000); self.assertEqual(d.lines.get().name,'নমুনা পণ্য')
        self.client.force_login(self.a); self.assertEqual(self.client.get(f'/documents/{d.pk}/edit/').status_code,403)
    def test_return_for_correction_resubmit_reject_and_audit(self):
        d=self.sale(); review(self.admin,d.pk,'return','Correct quantity')
        d.refresh_from_db(); self.assertEqual(d.status,'returned')
        create_document(self.a,self.ca,'sale',d.date,{'product':self.p,'quantity':2,'price':'1000','discount':'0'},True,d)
        review(self.admin,d.pk,'reject','Duplicate sample'); self.assertEqual(balance(self.ca),0)
        self.assertTrue(Audit.objects.filter(action='return',reason='Correct quantity').exists())
    def test_money_and_bad_inputs(self):
        self.assertEqual(money('0.29'),29)
        for value in ['NaN','Infinity','-1','1.001']:
            with self.assertRaises(ValidationError): money(value)
        for qty,discount in [(0,'0'),(-1,'0'),(1,'1001')]:
            with self.assertRaises(ValidationError): create_document(self.a,self.ca,'sale',date(2026,10,1),{'product':self.p,'quantity':qty,'price':'1000','discount':discount},True)
    def test_csrf_inactive_no_public_registration(self):
        c=Client(enforce_csrf_checks=True); self.assertEqual(c.post('/login/',{'username':'a','password':'test-only-password-532!'}).status_code,403)
        self.client.force_login(self.a); self.a.is_active=False; self.a.save(); self.assertEqual(self.client.get('/').status_code,302)
        self.assertEqual(self.client.get('/register/').status_code,404)
    def test_ui_pages_and_bengali_print_markup(self):
        d=self.sale(); review(self.admin,d.pk,'approve'); self.client.force_login(self.admin)
        for path in ['/','/customers/','/products/','/documents/','/new/sale/','/new/collection/','/users/','/activity/','/deliveries/',f'/deliveries/{d.delivery.pk}/',f'/documents/{d.pk}/',f'/customers/{self.ca.pk}/ledger/','/master/customers/new/','/master/products/new/']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        r=self.client.get(f'/documents/{d.pk}/'); self.assertContains(r,'নমুনা পণ্য'); self.assertContains(r,'@media print'); self.assertContains(r,'width=device-width'); self.assertContains(r,'Save as PDF')
    def test_http_form_invoice_and_collection(self):
        self.client.force_login(self.a)
        r=self.client.post('/new/sale/',{'customer':self.ca.pk,'date':'2026-10-05','product':self.p.pk,'quantity':5,'price':'1000.00','discount':'0','action':'submit'})
        self.assertEqual(r.status_code,302); self.assertEqual(Document.objects.get().amount,500000)
        r=self.client.post('/new/collection/',{'customer':self.ca.pk,'date':'2026-10-07','amount':'3000','method':'cash','reference':'WEB-REF','action':'submit'})
        self.assertEqual(r.status_code,302); self.assertEqual(Document.objects.count(),2)
    def test_master_opening_balance_and_staff_admin_boundaries(self):
        self.client.force_login(self.admin)
        r=self.client.post('/master/customers/new/',{'code':'OPEN-NEW','name':'New','contact':'Sample','phone':'','address':'Sample','area':'Sample','assigned':self.a.pk,'active':'on','opening_balance':'10000','opening_date':'2026-09-01'})
        # phone is required; submit an explicitly fictional number.
        if r.status_code==200:
            r=self.client.post('/master/customers/new/',{'code':'OPEN-NEW','name':'New','contact':'Sample','phone':'00000000000','address':'Sample','area':'Sample','assigned':self.a.pk,'active':'on','opening_balance':'10000','opening_date':'2026-09-01'})
        self.assertEqual(r.status_code,302); self.assertEqual(balance(Customer.objects.get(code='OPEN-NEW')),1000000)
        self.client.force_login(self.a)
        for path in ['/users/','/activity/','/master/products/new/','/master/customers/new/']:
            self.assertEqual(self.client.get(path).status_code,403)
    def test_multi_product_invoice_and_formset(self):
        self.client.force_login(self.a)
        r=self.client.post('/new/sale/',{'customer':self.ca.pk,'date':'2026-10-05','product':self.p.pk,'quantity':'2','price':'1000','discount':'50','action':'submit','lines-TOTAL_FORMS':'1','lines-INITIAL_FORMS':'0','lines-MIN_NUM_FORMS':'0','lines-MAX_NUM_FORMS':'19','lines-0-product':self.p.pk,'lines-0-quantity':'3','lines-0-price':'1000','lines-0-discount':'25'})
        self.assertEqual(r.status_code,302)
        d=Document.objects.get(); self.assertEqual(d.amount,492500); self.assertEqual(d.lines.count(),2)
        review(self.admin,d.pk,'approve'); self.assertEqual(balance(self.ca),492500)
    def test_adjustment_permissions_and_dates(self):
        d=self.sale(); review(self.admin,d.pk,'approve')
        with self.assertRaises(PermissionDenied): adjustment(self.a,d.pk,'50','Reason',date(2026,10,6))
        with self.assertRaises(ValidationError): adjustment(self.admin,d.pk,'50','',date(2026,10,6))
        with self.assertRaises(ValidationError): adjustment(self.admin,d.pk,'50','Reason',date(2026,10,1))
        self.assertEqual(Entry.objects.filter(document=d).count(),1)
