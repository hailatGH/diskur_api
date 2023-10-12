from django import forms
from moogts.models import Moogt
from arguments.models import Argument
from django.urls import reverse, reverse_lazy


class MoogtForm(forms.ModelForm):

    class Meta:
        model = Moogt
        fields = ['resolution']
        widgets = {
            'resolution': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ArgumentForm(forms.ModelForm):

    class Meta:
        model = Argument
        fields = ['argument']
        widgets = {
            'argument': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }


class MoogtAdditionalForm(forms.Form):
    argument = forms.CharField(widget=forms.Textarea(
        attrs={'rows': 4, 'class': 'form-control'}), label='Opening argument', max_length=500, required=True)

