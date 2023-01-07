import uuid
import json
import requests
import importlib
import hmac
import hashlib
import base64
from django.db import models
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver

from .signals import hook_event
from .models import WebHook, WebHookEvent, WebHookEventLog

client = requests.Session()

def serialize_hook_event(hook_event, payload):
    payload_string = json.dumps(payload, cls=DjangoJSONEncoder)
    digest = hmac.digest(hook_event.hook.secret.bytes, payload_string.encode('utf-8'), hashlib.sha256)

    return {
        'event': {
            'id': hook_event.id,
            'hook': hook_event.hook.id,
            'name': hook_event.event,
            'target': hook_event.hook.target,
            'signature': base64.b64encode(digest).decode('utf-8'),
        },
        'data': payload,
    }

def send(hook, event, payload):

    hook_event = enqueue(hook, event, payload)
    data = serialize_hook_event(hook_event, payload)
    print(data)

    resp = client.post(
        url=hook.target,
        data=json.dumps(data, cls=DjangoJSONEncoder),
        headers={'Content-Type': 'application/json'}
    )
    print(resp)
    WebHookEventLog.objects.create(
        event=hook_event,
        status=resp.status_code,
        response=resp.content
    )
    if resp.status_code == 200:
        hook_event.success=True
        hook_event.save()
    return hook_event

def enqueue(hook, event, payload):
    hook_event = WebHookEvent.objects.create(
        hook=hook,
        event=event,
        payload=payload,
    )
    return hook_event

def get_all_webhooks(community, event, payload):
    hooks = WebHook.objects.filter(community=community)
    for hook in hooks:
        if hook.event == event or (hook.event[-1] == '*' and event[:len(hook.event)-1] == hook.event[:-1]):
            yield(hook)

@receiver(hook_event, dispatch_uid='instance-custom-hook')
def hook_triggered(sender, community,
                          event,
                          payload,
                          **kwargs):
    """
    Manually trigger a custom action (or even a standard action).
    """
    print("Hook event fired: %s" % event)
    webhook_filter_module, webhook_filter_function = getattr(settings, 'WEBHOOK_FILTER', 'corm.webhooks.get_all_webhooks').rsplit('.', 1)
    module = importlib.import_module(webhook_filter_module)
    get_webhooks = getattr(module, webhook_filter_function)
    for hook in get_webhooks(community, event, payload):
        print("Checking hook: %s" % hook.event)
        if hook.event == event or (hook.event[-1] == '*' and event[:len(hook.event)-1] == hook.event[:-1]):
            print("Firing hook: %s" % hook.id )
            hook_event = send(
                hook=hook,
                event=event,
                payload=payload,
            )

