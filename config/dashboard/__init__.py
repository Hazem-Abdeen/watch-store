"""Add homepage management while retaining Oscar's dashboard apps and namespace."""
from django.urls import path
from oscar.apps.dashboard.apps import DashboardConfig as OscarDashboardConfig


class DashboardConfig(OscarDashboardConfig):
    name = 'config.dashboard'

    def configure_permissions(self):
        super().configure_permissions()
        # Same staff-only policy as Oscar's dashboard management areas. Partners
        # with dashboard access must not be able to change storefront campaigns.
        self.permissions_map.update({name: ['is_staff'] for name in (
            'hero-slide-list', 'hero-slide-create', 'hero-slide-update', 'hero-slide-delete',
            'brand-logo-list', 'brand-logo-update',
        )})

    def get_urls(self):
        from homepage import views

        urls = [
            path('homepage/brand-logos/', views.BrandLogoListView.as_view(), name='brand-logo-list'),
            path('homepage/brand-logos/<int:pk>/edit/', views.BrandLogoUpdateView.as_view(), name='brand-logo-update'),
            path('homepage/hero-slides/', views.HeroSlideListView.as_view(), name='hero-slide-list'),
            path('homepage/hero-slides/add/', views.HeroSlideCreateView.as_view(), name='hero-slide-create'),
            path('homepage/hero-slides/<int:pk>/edit/', views.HeroSlideUpdateView.as_view(), name='hero-slide-update'),
            path('homepage/hero-slides/<int:pk>/delete/', views.HeroSlideDeleteView.as_view(), name='hero-slide-delete'),
        ]
        return self.post_process_urls(urls) + super().get_urls()
