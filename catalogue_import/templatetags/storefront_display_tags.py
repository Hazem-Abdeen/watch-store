"""Hide optional storefront UI without disabling Oscar applications or URLs."""
from django import template
from django.conf import settings
from oscar.templatetags import display_tags

register = template.Library()
register.tags.update(display_tags.register.tags)
register.filters.update(display_tags.register.filters)


@register.simple_tag
def storefront_social_links():
    return getattr(settings, 'ABDEEN_SOCIAL_LINKS', ())


@register.simple_tag
def storefront_whatsapp_url():
    return getattr(settings, 'ABDEEN_WHATSAPP_URL', '')


def feature_visible(context, feature):
    request = context.get('request')
    match = getattr(request, 'resolver_match', None)
    if match and 'dashboard' in match.namespaces:
        return True
    return feature not in getattr(settings, 'ABDEEN_STOREFRONT_HIDDEN_FEATURES', ())


class StorefrontFeatureNode(template.Node):
    def __init__(self, original):
        self.original = original

    def render(self, context):
        if feature_visible(context, self.original.feature_name):
            return self.original.render(context)
        return ''


@register.tag
def iffeature(parser, token):
    return StorefrontFeatureNode(display_tags.iffeature(parser, token))


@register.simple_tag(takes_context=True)
def storefront_feature_visible(context, feature):
    return feature_visible(context, feature)
