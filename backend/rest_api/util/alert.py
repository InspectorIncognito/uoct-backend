import requests
import logging
from decouple import config

logger = logging.getLogger(__name__)


class TranSappSiteManager:

    def __init__(self):
        self.server_name = 'https://{0}'.format(config('TRANSAPP_HOST'))
        self.server_username = config('TRANSAPP_SITE_USERNAME')
        # urls
        self.LOGIN_URL = '{0}/user/login/'.format(self.server_name)
        self.CREATE_ALERT_URL = '{0}/alert/add/'.format(self.server_name)

        self.session = self.get_logged_session()

    def get_logged_session(self):
        payload = {
            'username': self.server_username,
            'password': config('TRANSAPP_SITE_PASSWORD'),
            'next': '/admin'
        }

        req_session = requests.Session()
        res = req_session.get(self.LOGIN_URL)
        csrf_token = res.cookies['csrftoken']
        payload['csrfmiddlewaretoken'] = csrf_token

        req_session.headers.update({'referer': self.LOGIN_URL})
        response = req_session.post(self.LOGIN_URL, data=payload, cookies=res.cookies)

        logger.info('se intenta iniciar sesión en "{0}" con usuario "{1}". Resultado: {2}'.format(
            self.server_name, self.server_username, response.status_code))

        return req_session

    def create_alert(self):
        pass