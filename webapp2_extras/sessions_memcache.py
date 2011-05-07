# -*- coding: utf-8 -*-
"""
    webapp2_extras.sessions_memcache
    ================================

    Extended sessions stored in memcache.

    :copyright: 2011 by tipfy.org.
    :license: Apache Sotware License, see LICENSE for details.
"""
from google.appengine.api import memcache

from webapp2_extras import sessions


class MemcacheSessionFactory(sessions.CustomBackendSessionFactory):
    """A session factory that stores data serialized in memcache.

    To use memcache sessions, pass this class as the `factory` keyword to
    :meth:`webapp2_extras.sessions.SessionStore.get_session`.
    """

    def _get_by_sid(self, sid):
        """Returns a session given a session id."""
        data = memcache.get(sid)
        if data is not None:
            return sessions.SessionDict(self, data=data)

        self.sid = self._get_new_sid()
        return sessions.SessionDict(self, new=True)

    def save_session(self, response):
        if self.session is None or not self.session.modified:
            return

        memcache.set(self.sid, dict(self.session))
        self.session_store.save_secure_cookie(
            response, self.name, {'_sid': self.sid}, **self.session_args)
