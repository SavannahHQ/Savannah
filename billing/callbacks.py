
def stripe_event_callback(event):
    data = event.json_body
    if data["type"] == "payment_method.detached":
        # https://github.com/dj-stripe/dj-stripe/issues/1068
        return
    event.process(save=False)
