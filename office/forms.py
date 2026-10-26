from django import forms
from django.contrib.auth.models import User
from .models import Customer, Product
class DocumentForm(forms.Form):
    customer=forms.ModelChoiceField(queryset=Customer.objects.none(),label='গ্রাহক')
    date=forms.DateField(label='তারিখ',widget=forms.DateInput(attrs={'type':'date'}))
    product=forms.ModelChoiceField(queryset=Product.objects.filter(active=True),label='পণ্য',required=False)
    quantity=forms.IntegerField(label='পরিমাণ (পূর্ণ ইউনিট)',min_value=1,initial=1,required=False)
    price=forms.DecimalField(label='একক মূল্য (BDT)',min_value=0,decimal_places=2,required=False)
    discount=forms.DecimalField(label='মোট ছাড় (BDT)',min_value=0,decimal_places=2,initial=0,required=False)
    amount=forms.DecimalField(label='আদায়ের পরিমাণ (BDT)',min_value=0,decimal_places=2,required=False)
    method=forms.ChoiceField(label='পেমেন্ট পদ্ধতি',choices=[('cash','নগদ'),('bank','ব্যাংক'),('mobile','মোবাইল ব্যাংকিং')],required=False)
    reference=forms.CharField(label='অনন্য লেনদেন রেফারেন্স',max_length=100,required=False)
    notes=forms.CharField(label='মন্তব্য',widget=forms.Textarea,required=False)
    def __init__(self,*args,user,kind,**kwargs):
        super().__init__(*args,**kwargs)
        from .services import customers
        self.fields['customer'].queryset=customers(user).filter(active=True)
        remove=['amount','method','reference'] if kind=='sale' else ['product','quantity','price','discount']
        for k in remove: del self.fields[k]
        for k in (['product','quantity','price','discount'] if kind=='sale' else ['amount','method','reference']): self.fields[k].required=True
class CustomerForm(forms.ModelForm):
    opening_balance=forms.DecimalField(label="প্রারম্ভিক বকেয়া BDT (নতুন গ্রাহক)",decimal_places=2,initial=0,required=False)
    opening_date=forms.DateField(label="প্রারম্ভিক স্থিতির কার্যকর তারিখ",widget=forms.DateInput(attrs={"type":"date"}),required=False)
    class Meta:
        model=Customer; fields=['code','name','contact','phone','address','area','assigned','active']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['assigned'].queryset=User.objects.filter(profile__role='field',is_active=True)
        if self.instance.pk:
            del self.fields['opening_balance']; del self.fields['opening_date']
    def clean(self):
        data=super().clean()
        if data.get('opening_balance') and not data.get('opening_date'): self.add_error('opening_date','Effective date required')
        return data
class ProductForm(forms.ModelForm):
    class Meta: model=Product; fields=['code','name','package','unit','price','active']
class UserForm(forms.Form):
    username=forms.CharField(max_length=150)
    password=forms.CharField(min_length=12,widget=forms.PasswordInput)
    role=forms.ChoiceField(choices=[('field','Field staff'),('delivery','Delivery staff'),('admin','Administrator')])
    phone=forms.CharField(max_length=24,required=False)

class ExtraLineForm(forms.Form):
    product=forms.ModelChoiceField(queryset=Product.objects.filter(active=True),label='পণ্য')
    quantity=forms.IntegerField(label='পরিমাণ',min_value=1,max_value=100000)
    price=forms.DecimalField(label='একক মূল্য BDT',min_value=0,decimal_places=2)
    discount=forms.DecimalField(label='মোট ছাড় BDT',min_value=0,decimal_places=2)
ExtraLines=forms.formset_factory(ExtraLineForm,extra=0,max_num=19,validate_max=True,can_delete=True)
