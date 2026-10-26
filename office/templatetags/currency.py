from django import template
from decimal import Decimal
register=template.Library()
@register.filter
def taka(value): return f'{Decimal(value or 0)/100:,.2f}'
