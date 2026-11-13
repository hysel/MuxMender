"""Shared ordering for the worker and the waiting list."""

ORDERS = {
    'added': 'Order added',
    'modified-newest': 'Last modified: newest first',
    'modified-oldest': 'Last modified: oldest first',
    'size-largest': 'File size: largest first',
    'size-smallest': 'File size: smallest first',
    'name': 'File name: A–Z',
}


def valid_order(value):
    return isinstance(value, str) and value in ORDERS


def waiting_key(job, order):
    # Stable sorting (and min's first-match behavior) retain insertion order
    # for equal values. Unknown values come last in either direction.
    if order == 'name':
        source = job.get('source')
        name = source.replace('\\', '/').rsplit('/', 1)[-1].casefold() if isinstance(source, str) else ''
        return not name, name
    index = 0 if order.startswith('size-') else 1
    signature = job.get('signature')
    value = signature[index] if isinstance(signature, (list, tuple)) and len(signature) > index else None
    if type(value) is not int or (index == 0 and value < 0):
        return True, 0
    return False, -value if order in ('size-largest', 'modified-newest') else value
