from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Умножение: {{ value|mul:arg }}"""
    try:
        return float(value) * float(arg)
    except:
        return 0

@register.filter
def div(value, arg):
    """Деление: {{ value|div:arg }}"""
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except:
        return 0

@register.filter
def percent(value, arg):
    """Процент: {{ part|percent:total }} → (part/total)*100"""
    try:
        total = float(arg)
        if total == 0:
            return 0
        return (float(value) / total) * 100
    except:
        return 0
