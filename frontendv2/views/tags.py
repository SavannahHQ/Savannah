import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.contrib import messages
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView

class Tags(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "tags"

    def all_tags(self):
        return Tag.objects.filter(community=self.community).annotate(channel_count=Count('channel', distinct=True), member_count=Count('member', distinct=True))

    @login_required
    def as_view(request, community_id):
        view = Tags(request, community_id)
        if request.method == 'POST':
            if 'delete_tag' in request.POST:
                tag = get_object_or_404(Tag, id=request.POST.get('delete_tag'))
                context = view.context
                context.update({
                    'object_type':"Tag", 
                    'object_name': tag.name, 
                    'object_id': tag.id,
                    'warning_msg': "This will remove the tag from all Members, Conversations and Contributions",
                })
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                tag = get_object_or_404(Tag, id=request.POST.get('object_id'))
                tag_name = tag.name
                tag.delete()
                messages.success(request, "Deleted tag: <b>%s</b>" % tag_name)

                return redirect('tags', community_id=community_id)

        return render(request, "savannahv2/tags.html", view.context)

class TagEditForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name', 'color', 'keywords']
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color'}),
        }
    def __init__(self, *args, **kwargs):
        super(TagEditForm, self).__init__(*args, **kwargs)
        if 'color' in self.initial:
            self.initial['color'] = '#%s'%self.initial['color']

    def clean_color(self):
        data = self.cleaned_data['color']
        return data.replace('#', '')
        
class AddTag(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.edit_tag = Tag(community=self.community, color="E5E6E8", last_changed=datetime.datetime.utcnow())
        self.active_tab = "tags"

    @property
    def form(self):
        if self.request.method == 'POST':
            return TagEditForm(instance=self.edit_tag, data=self.request.POST)
        else:
            return TagEditForm(instance=self.edit_tag)

    @login_required
    def as_view(request, community_id):
        view = AddTag(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('tags', community_id=community_id)

        return render(request, "savannahv2/tag_add.html", view.context)

class EditTag(SavannahView):
    def __init__(self, request, tag_id):
        self.edit_tag = get_object_or_404(Tag, id=tag_id)
        super().__init__(request, self.edit_tag.community.id)
        self.active_tab = "tags"

    @property
    def form(self):
        if self.request.method == 'POST':
            return TagEditForm(instance=self.edit_tag, data=self.request.POST)
        else:
            return TagEditForm(instance=self.edit_tag)

    @login_required
    def as_view(request, tag_id):
        view = EditTag(request, tag_id)
        keywords = view.edit_tag.keywords
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            if view.edit_tag.keywords != keywords:
                view.edit_tag.last_changed = datetime.datetime.utcnow()
                view.edit_tag.save()
            return redirect('tags', community_id=view.community.id)

        return render(request, "savannahv2/tag_edit.html", view.context)
