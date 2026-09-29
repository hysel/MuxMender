"""Shared size-aware savings requirements; decimal GB/MB, no quality changes."""
import math
from fractions import Fraction


def requirement(source_bytes, mode='fixed', percent=25):
    if type(source_bytes) is not int or source_bytes<=0:
        raise ValueError('Savings require a positive source size')
    if mode not in ('fixed','size-aware'):
        raise ValueError('Unknown savings mode')
    if type(percent) not in (int,float) or not math.isfinite(percent) or not 0<=percent<100:
        raise ValueError('Invalid savings percentage')
    exact=source_bytes*Fraction(str(percent))/100
    needed=(exact.numerator+exact.denominator-1)//exact.denominator
    if mode=='size-aware':
        needed=max(100_000_000,min((source_bytes+3)//4,1_000_000_000))
    return dict(mode=mode,source_bytes=source_bytes,required_bytes=needed,
                effective_percent=100*needed/source_bytes,possible=needed<source_bytes)


def meets_requirement(source_bytes, output_bytes, policy):
    """Apply the original byte target, without percentage round-trip errors."""
    if type(source_bytes) is not int or type(output_bytes) is not int or min(source_bytes,output_bytes)<=0:
        raise ValueError('Savings require positive integer source and output sizes')
    needed=policy.get('required_bytes')
    if policy.get('source_bytes')!=source_bytes or type(needed) is not int or needed<0:
        raise ValueError('Savings policy does not match the source size')
    return output_bytes<source_bytes and source_bytes-output_bytes>=needed
