from pathlib import Path

from odoo import http
from odoo.http import request


class NutKingsWorkspace(http.Controller):
    MODULE_PATH = Path(__file__).resolve().parents[1]

    @http.route('/nutkings', type='http', auth='user', methods=['GET'])
    def workspace_redirect(self, **kwargs):
        return request.redirect('/nutkings/')

    @http.route(['/nutkings/', '/nutkings/offline', '/nutkings/rapid-scan'], type='http', auth='user', methods=['GET'])
    def workspace(self, **kwargs):
        content = (self.MODULE_PATH / 'static' / 'workspace' / 'index.html').read_text(encoding='utf-8')
        return request.make_response(content, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-cache, must-revalidate'),
            ('X-Content-Type-Options', 'nosniff'),
        ])

    @http.route('/nutkings/reset', type='http', auth='user', methods=['GET'])
    def reset(self, **kwargs):
        content = (self.MODULE_PATH / 'static' / 'workspace' / 'reset.html').read_text(encoding='utf-8')
        return request.make_response(content, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store, max-age=0'),
        ])

    @http.route('/nutkings/sw.js', type='http', auth='public', methods=['GET'], csrf=False)
    def service_worker(self, **kwargs):
        content = (self.MODULE_PATH / 'static' / 'workspace' / 'sw.js').read_text(encoding='utf-8')
        return request.make_response(content, headers=[
            ('Content-Type', 'application/javascript; charset=utf-8'),
            ('Service-Worker-Allowed', '/nutkings/'),
            ('Cache-Control', 'no-cache, must-revalidate'),
        ])

    @http.route('/nutkings/manifest.webmanifest', type='http', auth='public', methods=['GET'], csrf=False)
    def manifest(self, **kwargs):
        content = (self.MODULE_PATH / 'static' / 'workspace' / 'manifest.webmanifest').read_text(encoding='utf-8')
        return request.make_response(content, headers=[
            ('Content-Type', 'application/manifest+json'),
            ('Cache-Control', 'no-cache, must-revalidate'),
        ])

    @http.route('/nutkings/backend', type='http', auth='user', methods=['GET'])
    def backend(self, **kwargs):
        action = request.env.ref('nut_kings_ops.action_nk_backend_dashboard')
        menu = request.env.ref('nut_kings_ops.menu_nk_backend_dashboard')
        return request.redirect(f'/web#action={action.id}&menu_id={menu.id}')
