"""Real separate-connection approval race against an isolated temporary SQLite file."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
from django.conf import settings
with tempfile.TemporaryDirectory() as directory:
    settings.DATABASES['default']['NAME']=Path(directory)/'race.sqlite3'
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate',verbosity=0)
    from django.contrib.auth.models import User
    from django.db import connections
    from office.models import Profile, Customer, Product, Entry, Delivery
    from office.services import create_document, review
    from datetime import date
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    admin=User.objects.create_user('race-admin'); Profile.objects.create(user=admin,role='admin')
    staff=User.objects.create_user('race-field'); Profile.objects.create(user=staff,role='field')
    c=Customer.objects.create(code='RACE',name='Fictional',contact='Sample',phone='',address='Sample',area='Sample',assigned=staff)
    p=Product.objects.create(code='RACE',name='Sample',package='Fictional',unit='pack',price=10000)
    d=create_document(staff,c,'sale',date(2026,10,1),dict(product=p.pk,quantity=1,price='100',discount='0'),True)
    barrier=Barrier(2)
    def approve(_):
        try:
            user=User.objects.get(pk=admin.pk); barrier.wait(timeout=10)
            return review(user,d.pk,'approve').number
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool: numbers=list(pool.map(approve,range(2)))
    assert numbers[0]==numbers[1] and numbers[0]
    assert Entry.objects.filter(document=d,kind='sale').count()==1
    assert Delivery.objects.filter(document=d).count()==1
    print('PASS: two concurrent approval connections return the same final number; exactly one ledger posting and delivery.')
    connections.close_all()
