"""Pure admission-order experiment. Not enabled in the production scheduler."""
import math


def valid(ticket):
    return (isinstance(ticket,dict) and type(ticket.get('sequence')) is int and
            ticket['sequence']>=0 and type(ticket.get('seconds')) in (int,float) and
            math.isfinite(ticket['seconds']) and ticket['seconds']>0 and
            type(ticket.get('bypasses',0)) is int and 0<=ticket.get('bypasses',0)<=2)


def choose(waiting):
    """At most two short admissions can pass each earlier waiting long stage."""
    if not waiting:return None
    if any(not isinstance(t,dict) or type(t.get('sequence')) is not int or t['sequence']<0 for t in waiting):
        raise ValueError('Invalid ticket sequence')
    if len({t['sequence'] for t in waiting})!=len(waiting):raise ValueError('Duplicate ticket sequence')
    # Unknown/legacy information is not evidence for reordering.
    if any(not valid(t) for t in waiting):return min(waiting,key=lambda t:t['sequence'])
    forced=[t for t in waiting if t['seconds']>60 and t.get('bypasses',0)>=2]
    if forced:return min(forced,key=lambda t:t['sequence'])
    short=[t for t in waiting if t['seconds']<=60]
    return min(short or waiting,key=lambda t:t['sequence'])


def admitted(waiting,selected):
    """Return new records; a real coordinator would persist these under its lock."""
    rows=[]
    for ticket in waiting:
        if ticket['sequence']==selected['sequence']:continue
        row=dict(ticket)
        if (valid(row) and valid(selected) and selected['seconds']<=60 and
                row['seconds']>60 and row['sequence']<selected['sequence']):
            row['bypasses']=min(2,row.get('bypasses',0)+1)
        rows.append(row)
    return rows
