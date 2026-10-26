import secrets
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth.models import User
from office.models import *
from office.services import create_document, review, adjustment

class Command(BaseCommand):
    help='Seed fictional local data; generates random passwords in data/demo-accounts.txt. Never use in production.'
    @transaction.atomic
    def handle(self,*args,**options):
        if User.objects.exists():
            self.stdout.write('Accounts already exist; no data or passwords changed.'); return
        credentials=[]; users={}
        for name,role in [('admin','admin'),('field_a','field'),('field_b','field'),('delivery_a','delivery'),('delivery_b','delivery')]:
            password=secrets.token_urlsafe(18)
            u=User.objects.create_user(username=name,password=password); Profile.objects.create(user=u,role=role)
            users[name]=u; credentials.append(f'{name}: {password}')
        a=Customer.objects.create(code='DEMO-A',name='কাল্পনিক মৎস্য খামার A',contact='নমুনা ব্যক্তি A',phone='',address='কাল্পনিক ঠিকানা, ঢাকা',area='নমুনা ঢাকা',assigned=users['field_a'])
        Customer.objects.create(code='DEMO-B',name='কাল্পনিক মৎস্য খামার B',contact='নমুনা ব্যক্তি B',phone='',address='কাল্পনিক ঠিকানা, খুলনা',area='নমুনা খুলনা',assigned=users['field_b'])
        products=[]
        for i,name in enumerate(['SB HYDROMIN','Hepamin Plus','MB 30','Grow Max','Bio Boost']):
            products.append(Product.objects.create(code=f'DEMO-P{i+1}',name=name,package='FICTIONAL SAMPLE 1 unit pack',unit='sample pack',price=100000))
        Entry.objects.create(customer=a,date=date(2026,9,1),kind='opening',reference='DEMO-OPEN',description='Fictional opening BDT 10,000',debit=1000000,actor=users['admin'])
        d=create_document(users['field_a'],a,'sale',date(2026,10,5),{'product':products[0].pk,'quantity':5,'price':'1000','discount':'0'},True)
        review(users['admin'],d.pk,'approve')
        adjustment(users['admin'],d.pk,'500','Fictional sample credit return',date(2026,10,6))
        c=create_document(users['field_a'],a,'collection',date(2026,10,7),{'amount':'3000','method':'cash','reference':'DEMO-REF-001'},True)
        review(users['admin'],c.pk,'approve')
        from django.conf import settings
        path=settings.DATA/'demo-accounts.txt'; path.write_text('LOCAL DEVELOPMENT ONLY · FICTIONAL SAMPLE DATA\n'+'\n'.join(credentials)+'\n'); path.chmod(0o600)
        self.stdout.write(f'Fictional seed created. Generated development credentials: {path} (not printed). October closing / November opening = BDT 11,500.')
