from django.conf import settings
from shoppingcart.processors.helpers import get_processor_config
from edxmako.shortcuts import render_to_string
from shoppingcart.models import Order
from django.http import HttpResponse
from django.core.urlresolvers import reverse
import logging
import json

log = logging.getLogger(__name__)


def get_description(shoppingcart_items):
    description = ''
    for item, course in shoppingcart_items:
        if int(item.qty) > 1:
            description += (u'Course "{course}" - '
                           u'for {qty} students\n').format(
                               course=course.display_name,
                               qty=item.qty,
                               )
        else:
            description += (u'Course "{course}"').format(
                               course=course.display_name,
                               )
    return description


def render_purchase_form_html(cart, callback_url=''):
    from shoppingcart.views import verify_for_closed_enrollment
    shoppingcart_items = verify_for_closed_enrollment(cart.user, cart)[-1]
    return render_to_string('shoppingcart/stripe_form.html', {
        'action': reverse('shoppingcart.views.pay_stripe'),
        'src': 'https://checkout.stripe.com/checkout.js',
        'public_key': get_processor_config().get('PUBLIC_KEY'),
        'amount': int(cart.total_cost)*100, # amount in cents
        'name': 'Payment for:',
        'description': get_description(shoppingcart_items),
        'image': '/static/themes/default/images/pay_logo.png'
    })


def process_postpay_callback(params):
    params = json.loads(params)
    status = params['status']
    recieved_order = params['metadata']['order_id']
    order = Order.objects.get(id=int(recieved_order))
    if status == 'succeeded':
        _record_purchase(params, order)
        log.info('Success payment for order {}'.format(order.id))
        return {
            'success': True,
            'order': order,
            'error_html': ''
        }
    else:
        log.info('Unsuccessfull payment for order {}'.format(order.id))
        return {
                'success': False,
                'order': order,
                'error_html': _format_error_html(u'Message is: {msg}'.format(msg=params.get('failure_message')
                                                                            )
                                                )
               }


def _format_error_html(msg):
    """ Format an HTML error message """
    return u'<p class="error_msg">{msg}</p>'.format(msg=msg)


def _record_purchase(params, order):
    """
    Record the purchase and run purchased_callbacks
    """
    order.purchase(
        first=params['source'].get('name') or '',
        country=params['source'].get('address_country') or '',
        cardtype=params['source'].get('brand') or '',
        city=params['source'].get('address_city') or '',
        state=params['source'].get('address_state') or '',
        street1=params['source'].get('address_line1') or '',
        street2=params['source'].get('address_line2') or '',
        postalcode=params['source'].get('address_zip') or '',
        ccnum=params['source'].get('last4') or '',
        processor_reply_dump=params
    )

