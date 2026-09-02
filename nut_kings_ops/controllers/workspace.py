from pathlib import Path

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.addons.web.controllers.utils import _get_login_redirect_url, ensure_db
from odoo.http import request


class NutKingsWorkspace(http.Controller):
    MODULE_PATH = Path(__file__).resolve().parents[1]

    @staticmethod
    def _landing_url(user):
        permissions = user.nk_ops_permissions()
        if permissions['manager']:
            return '/nutkings/#dashboard'
        if permissions['dispatcher']:
            return '/nutkings/#distribution'
        if permissions['finished_goods_entry']:
            return '/nutkings/#finished'
        if permissions['raw']:
            return '/nutkings/#raw'
        return '/nutkings/'

    @staticmethod
    def _has_workspace_access():
        return bool(request.session.uid and request.env.user.nk_ops_permissions()['has_nutkings_access'])

    @staticmethod
    def _login_response(error=None, login=None, status=200):
        response = request.render('nut_kings_ops.workspace_login_page', {
            'error': error,
            'login': login or request.session.get('auth_login') or '',
        })
        response.status_code = status
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'"
        return response

    @staticmethod
    def _forbidden():
        return request.make_response(
            'Your user does not have a Nut Kings operational role. Ask a Nut Kings manager to update the account under Workspace Users.',
            status=403,
            headers=[('Content-Type', 'text/plain; charset=utf-8')],
        )

    @http.route('/nutkings/login', type='http', auth='none', methods=['GET', 'POST'], readonly=False)
    def workspace_login(self, **kwargs):
        ensure_db()
        if request.env.uid is None:
            if request.session.uid is None:
                request.env['ir.http']._auth_method_public()
            else:
                request.update_env(user=request.session.uid)

        if request.httprequest.method == 'GET' and request.session.uid:
            if request.env.user.nk_ops_permissions()['has_nutkings_access']:
                return request.redirect(self._landing_url(request.env.user), 303)
            request.session.logout(keep_db=True)
            return self._login_response('This account is not assigned to the Nut Kings Ops Workspace.')

        login = str(kwargs.get('login') or '').strip()
        if request.httprequest.method == 'POST':
            password = kwargs.get('password') or ''
            if not login or not password:
                return self._login_response('Enter your workspace username and password.', login)
            try:
                auth_info = request.session.authenticate(request.env, {
                    'login': login,
                    'password': password,
                    'type': 'password',
                })
                user = request.env(user=auth_info['uid']).user
                if not user.nk_ops_permissions()['has_nutkings_access']:
                    request.session.logout(keep_db=True)
                    return self._login_response(
                        'Your account does not have a Nut Kings operational role. Contact your Nut Kings manager.',
                        login,
                        status=403,
                    )
                redirect = self._landing_url(user)
                return request.redirect(_get_login_redirect_url(auth_info['uid'], redirect=redirect), 303)
            except AccessDenied:
                return self._login_response('The username or password is incorrect.', login, status=401)
        return self._login_response(login=login)

    @http.route('/nutkings/logout', type='http', auth='none', methods=['GET'], csrf=False)
    def workspace_logout(self, **kwargs):
        request.session.logout(keep_db=True)
        return request.redirect('/nutkings/login', 303)

    @http.route('/nutkings', type='http', auth='public', methods=['GET'])
    def workspace_redirect(self, **kwargs):
        if not request.session.uid:
            return request.redirect('/nutkings/login', 303)
        if not self._has_workspace_access():
            return self._forbidden()
        return request.redirect('/nutkings/')

    @http.route(['/nutkings/', '/nutkings/offline', '/nutkings/rapid-scan'], type='http', auth='public', methods=['GET'])
    def workspace(self, **kwargs):
        if not request.session.uid:
            return request.redirect('/nutkings/login', 303)
        if not self._has_workspace_access():
            return self._forbidden()
        content = (self.MODULE_PATH / 'static' / 'workspace' / 'index.html').read_text(encoding='utf-8')
        return request.make_response(content, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-cache, must-revalidate'),
            ('X-Content-Type-Options', 'nosniff'),
        ])

    @http.route('/nutkings/reset', type='http', auth='public', methods=['GET'])
    def reset(self, **kwargs):
        if not request.session.uid:
            return request.redirect('/nutkings/login', 303)
        if not self._has_workspace_access():
            return self._forbidden()
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
        if not request.env.user.nk_ops_permissions()['system']:
            return self._forbidden()
        dashboard = request.env['nutkings.backend.dashboard']._get_company_dashboard()
        action = request.env.ref('nut_kings_ops.action_nk_backend_dashboard')
        menu = request.env.ref('nut_kings_ops.menu_nk_backend_dashboard')
        return request.redirect(f'/web#action={action.id}&id={dashboard.id}&model=nutkings.backend.dashboard&view_type=form&menu_id={menu.id}')
