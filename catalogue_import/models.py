"""Private import bookkeeping, deliberately absent from admin and Oscar forms."""

from django.db import models


class CatalogueSource(models.Model):
    source = models.CharField(max_length=64, editable=False)
    source_id = models.PositiveBigIntegerField(editable=False)
    product = models.OneToOneField('catalogue.Product', on_delete=models.PROTECT, related_name='+')
    stockrecord = models.OneToOneField('partner.StockRecord', on_delete=models.PROTECT, related_name='+')
    image = models.ForeignKey('catalogue.ProductImage', null=True, blank=True,
                              on_delete=models.SET_NULL, related_name='+')
    image_url = models.TextField(blank=True, editable=False)
    metadata = models.JSONField(default=dict, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('source', 'source_id'), name='unique_catalogue_source')]
