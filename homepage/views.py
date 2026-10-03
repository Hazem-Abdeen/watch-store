from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, FormView, TemplateView, UpdateView

from .brands import brand_categories
from .forms import BrandLogoForm, HeroSlideForm, HeroSlideOrderFormSet
from .models import BrandPresentation, HomeHeroSlide


class HeroSlideListView(TemplateView):
    template_name = 'oscar/dashboard/homepage/slide_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('formset', HeroSlideOrderFormSet(queryset=HomeHeroSlide.objects.all()))
        return context

    def post(self, request, *args, **kwargs):
        formset = HeroSlideOrderFormSet(request.POST, queryset=HomeHeroSlide.objects.all())
        if formset.is_valid():
            with transaction.atomic():
                formset.save()
            messages.success(request, 'Slide order and active status saved.')
            return redirect('dashboard:hero-slide-list')
        return self.render_to_response(self.get_context_data(formset=formset))


class HeroSlideCreateView(SuccessMessageMixin, CreateView):
    model = HomeHeroSlide
    form_class = HeroSlideForm
    template_name = 'oscar/dashboard/homepage/slide_form.html'
    success_url = reverse_lazy('dashboard:hero-slide-list')
    success_message = 'Hero slide saved.'


class HeroSlideUpdateView(SuccessMessageMixin, UpdateView):
    model = HomeHeroSlide
    form_class = HeroSlideForm
    template_name = 'oscar/dashboard/homepage/slide_form.html'
    success_url = reverse_lazy('dashboard:hero-slide-list')
    success_message = 'Hero slide saved.'


class HeroSlideDeleteView(SuccessMessageMixin, DeleteView):
    model = HomeHeroSlide
    template_name = 'oscar/dashboard/homepage/slide_confirm_delete.html'
    success_url = reverse_lazy('dashboard:hero-slide-list')
    success_message = 'Hero slide deleted.'


class BrandLogoListView(TemplateView):
    template_name = 'oscar/dashboard/homepage/brand_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['brands'] = brand_categories()
        return context


class BrandLogoUpdateView(FormView):
    template_name = 'oscar/dashboard/homepage/brand_form.html'
    form_class = BrandLogoForm
    success_url = reverse_lazy('dashboard:brand-logo-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.category = get_object_or_404(brand_categories(), pk=self.kwargs['pk'])
        try:
            presentation = self.category.brand_presentation
        except BrandPresentation.DoesNotExist:
            presentation = BrandPresentation(category=self.category)
        kwargs['instance'] = presentation
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Brand logo saved.')
        return super().form_valid(form)
