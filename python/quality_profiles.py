"""Shared quality acceptance policy, independent of encoder tuning."""
import math

PROFILES = {
    'strict': {'label': 'Strict', 'mean': 95, 'p5': 90},
    'balanced': {'label': 'Balanced', 'mean': 94, 'p5': 90},
    'space-saver': {'label': 'Space saver', 'mean': 90, 'p5': 90},
}


def profile(identifier):
    if not isinstance(identifier, str) or identifier not in PROFILES:
        raise ValueError('Unknown quality profile')
    return dict(PROFILES[identifier], id=identifier)


def apply_profile(args, output_policy):
    """Keep legacy jobs unchanged; explicit profiles replace resolution floors."""
    identifier = getattr(args, 'quality_profile', None)
    if identifier is None:
        if args.output_preset != 'original':
            args.vmaf_mean = max(args.vmaf_mean, output_policy['mean'])
            args.vmaf_p5 = max(args.vmaf_p5, output_policy['p5'])
    else:
        selected = profile(identifier)
        args.vmaf_mean = max(args.vmaf_mean, selected['mean'])
        args.vmaf_p5 = max(args.vmaf_p5, selected['p5'])
    return dict(id=identifier or 'legacy', mean=args.vmaf_mean, p5=args.vmaf_p5)


def validate_policy(policy):
    """Validate a recorded effective policy before using it for selection."""
    if not isinstance(policy, dict):
        raise ValueError('Missing quality policy')
    identifier = policy.get('id')
    floors = dict(mean=0,p5=0) if identifier == 'legacy' else profile(identifier)
    for key in ('mean','p5'):
        value = policy.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not floors[key] <= value <= 100:
            raise ValueError('Invalid quality policy threshold: '+key)
    return dict(id=identifier,mean=policy['mean'],p5=policy['p5'])


def scores_meet_policy(scores, policy):
    """Numeric evidence must support the producer's pass flag, not replace it."""
    policy = validate_policy(policy)
    if not isinstance(scores,dict) or scores.get('passed') is not True:
        return False
    for key in ('mean','p5'):
        value = scores.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not policy[key] <= value <= 100:
            return False
    return type(scores.get('frames')) is int and scores['frames'] > 0
