import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from haystack import connections
from oscar.core.loading import get_model

logger = logging.getLogger(__name__)


@receiver(post_save, sender=get_model('catalogue', 'ProductImage'), dispatch_uid='storefront_image_search_update')
def image_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return  # Transfers rebuild after the complete import.
    product_id = instance.product_id

    def update():
        product = get_model('catalogue', 'Product').objects.filter(pk=product_id).first()
        if product is None:
            return
        try:
            index = connections['default'].get_unified_index().get_index(type(product))
            index.update_object(product)
        except Exception:
            logger.exception('Image saved but search update failed for product %s; rebuild_index required.', product_id)
    transaction.on_commit(update)
