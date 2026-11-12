from django.db import models


class OrderEmailNotification(models.Model):
    """One automatic delivery attempt per order and audience, across processes."""

    order = models.ForeignKey('order.Order', on_delete=models.CASCADE, related_name='email_notifications')
    kind = models.CharField(max_length=16, choices=[('customer', 'Customer'), ('merchant', 'Merchant')])
    status = models.CharField(max_length=16, default='sending', choices=[
        ('sending', 'Sending'), ('sent', 'Sent'), ('failed', 'Failed'),
        ('uncertain', 'Delivery uncertain'), ('skipped', 'Skipped')])
    attempted_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_type = models.CharField(max_length=128, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'kind'], name='unique_order_email_audience')]
