"""Discovery for the bundled API; never launches work or reads media."""
from app_version import VERSION


def describe(*, controls=False):
    endpoints={'jobs':{'method':'GET','path':'/api/jobs'}}
    if controls:
        endpoints.update({
            'queue':{'method':'GET','path':'/api/controls'},
            'media':{'method':'GET','path':'/api/media'},
            'request_log':{'method':'GET','path':'/api/request-log'},
            'actions':{'method':'POST','path':'/api/control'},
        })
    return dict(api_version=1,app_version=VERSION,controls_enabled=controls,
                endpoints=endpoints,
                access='Trusted network only. Do not expose directly to the internet.',
                writes=dict(content_type='application/json',
                            origin='http://<dashboard-host>:<port>',
                            token_header='X-MuxMender-CSRF',
                            token_source='/api/controls' if controls else None,
                            note='The control token prevents cross-site writes; it is not authentication.'))
