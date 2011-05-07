# -*- coding: utf-8 -*-
"""
    webapp2_extras.sessions
    =======================

    Lightweight but robust session support for webapp2.

    :copyright: 2011 by tipfy.org.
    :license: Apache Sotware License, see LICENSE for details.
"""
import uuid
import re

import webapp2

from webapp2_extras import config as webapp_config
from webapp2_extras import securecookie

#: Default configuration values for this module. Keys are:
#:
#: secret_key
#:     Secret key to generate session cookies. Set this to something random
#:     and unguessable. Default is `REQUIRED_VALUE` (an exception
#:     is raised if it is not set).
#:
#: cookie_name
#:     Name of the cookie to save a session or session id. Default is
#:     `session`.
#:
#: session_max_age:
#:     Default session expiration time in seconds. Limits the duration of the
#:     contents of a cookie, even if a session cookie exists. If None, the
#:     contents lasts as long as the cookie is valid. Default is None.
#:
#: cookie_args
#:     Default keyword arguments used to set a cookie. Keys are:
#:
#:     - max_age: Cookie max age in seconds. Limits the duration
#:       of a session cookie. If None, the cookie lasts until the client
#:       is closed. Default is None.
#:
#:     - domain: Domain of the cookie. To work accross subdomains the
#:       domain must be set to the main domain with a preceding dot, e.g.,
#:       cookies set for `.mydomain.org` will work in `foo.mydomain.org` and
#:       `bar.mydomain.org`. Default is None, which means that cookies will
#:       only work for the current subdomain.
#:
#:     - path: Path in which the authentication cookie is valid.
#:       Default is `/`.
#:
#:     - secure: Make the cookie only available via HTTPS.
#:
#:     - httponly: Disallow JavaScript to access the cookie.
default_config = {
    'secret_key':      webapp_config.REQUIRED_VALUE,
    'cookie_name':     'session',
    'session_max_age': None,
    'cookie_args': {
        'max_age':     None,
        'domain':      None,
        'path':        '/',
        'secure':      None,
        'httponly':    False,
    }
}


class _UpdateDictMixin(object):
    """Makes dicts call `self.on_update` on modifications.

    From werkzeug.datastructures.
    """

    on_update = None

    def calls_update(name):
        def oncall(self, *args, **kw):
            rv = getattr(super(_UpdateDictMixin, self), name)(*args, **kw)
            if self.on_update is not None:
                self.on_update()
            return rv
        oncall.__name__ = name
        return oncall

    __setitem__ = calls_update('__setitem__')
    __delitem__ = calls_update('__delitem__')
    clear = calls_update('clear')
    pop = calls_update('pop')
    popitem = calls_update('popitem')
    setdefault = calls_update('setdefault')
    update = calls_update('update')
    del calls_update


class SessionDict(_UpdateDictMixin, dict):
    """A dictionary for session data."""

    __slots__ = ('container', 'new', 'modified')

    def __init__(self, container, data=None, new=False):
        self.container = container
        self.new = new
        self.modified = False
        dict.update(self, data or ())

    def on_update(self):
        self.modified = True

    def get_flashes(self, key='_flash'):
        """Returns a flash message. Flash messages are deleted when first read.

        :param key:
            Name of the flash key stored in the session. Default is '_flash'.
        :returns:
            The data stored in the flash, or an empty list.
        """
        if key not in self:
            # Avoid popping if the key doesn't exist to not modify the session.
            return []

        return self.pop(key, [])

    def add_flash(self, value, level=None, key='_flash'):
        """Adds a flash message. Flash messages are deleted when first read.

        :param value:
            Value to be saved in the flash message.
        :param level:
            An optional level to set with the message. Default is `None`.
        :param key:
            Name of the flash key stored in the session. Default is '_flash'.
        """
        self.setdefault(key, []).append((value, level))


class BaseSessionFactory(object):
    """Base class for all session factories."""

    #: Name of the session.
    name = None
    #: A reference to :class:`SessionStore`.
    session_store = None
    #: Keyword arguments to save the session.
    session_args = None
    #: The session data, a :class:`SessionDict` instance.
    session = None

    def __init__(self, name, session_store):
        self.name = name
        self.session_store = session_store
        self.session_args = session_store.config['cookie_args'].copy()
        self.session = None

    def get_session(self, max_age=webapp_config.DEFAULT_VALUE):
        raise NotImplementedError()

    def save_session(self, response):
        raise NotImplementedError()


class SecureCookieSessionFactory(BaseSessionFactory):
    """A session factory that stores data serialized in a signed cookie.

    This is the default factory passed as the `factory` keyword to
    :meth:`SessionStore.get_session`.
    """

    def get_session(self, max_age=webapp_config.DEFAULT_VALUE):
        if self.session is None:
            data = self.session_store.get_secure_cookie(self.name,
                                                        max_age=max_age)
            new = data is None
            self.session = SessionDict(self, data=data, new=new)

        return self.session

    def save_session(self, response):
        if self.session is None or not self.session.modified:
            return

        self.session_store.save_secure_cookie(
            response, self.name, dict(self.session), **self.session_args)


class CustomBackendSessionFactory(BaseSessionFactory):
    """Base class for sessions that use custom backends, e.g., memcache."""

    #: The session unique id.
    sid = None

    #: Used to validate session ids.
    _sid_re = re.compile(r'^[a-f0-9]{32}$')

    def get_session(self, max_age=webapp_config.DEFAULT_VALUE):
        if self.session is None:
            data = self.session_store.get_secure_cookie(self.name,
                                                        max_age=max_age)
            if data is not None:
                sid = data.get('_sid')
                if self._is_valid_sid(sid):
                    self.sid = sid
                    self.session = self._get_by_sid(sid)

            if self.session is None:
                self.sid = self._get_new_sid()
                self.session = SessionDict(self, new=True)

        return self.session

    def _is_valid_sid(self, sid):
        """Check if a session id has the correct format."""
        return sid and self._sid_re.match(sid) is not None

    def _get_by_sid(self, sid):
        raise NotImplementedError()

    def _get_new_sid(self):
        return uuid.uuid4().hex


class SessionStore(object):
    """A session provider.

    To use, define a base handler that extends the dispatch() method to start
    the session store and save all sessions at the end of a request::

        import webapp2

        from webapp2_extras import sessions

        class BaseHandler(webapp2.RequestHandler):
            def dispatch(self):
                # Start the session store.
                self.session_store = sessions.SessionStore(self.request)

                # Dispatch the request.
                webapp2.RequestHandler.dispatch(self)

                # Save all sessions.
                self.session_store.save_sessions(self.response)

            @webapp2.cached_property
            def session(self):
                # Returns a session using the default cookie key.
                return self.session_store.get_session()

    Then just use the session as a dictionary inside a handler::

        # To set a value:
        self.session['foo'] = 'bar'

        # To get a value:
        foo = self.session.get('foo')
    """
    def __init__(self, request):
        """Initializes the session store.

        :param request:
            A :class:`webapp2.Request` instance.
        """
        self.request = request
        # Base configuration.
        self.config = request.app.config[__name__]
        # Tracked sessions.
        self.sessions = {}
        # Serializer and deserializer for signed cookies.
        secret_key = self.config['secret_key']
        self.serializer = securecookie.SecureCookieSerializer(secret_key)

    # Backend based sessions --------------------------------------------------

    def _get_session_container(self, name, factory):
        if name not in self.sessions:
            self.sessions[name] = factory(name, self)

        return self.sessions[name]

    def get_session(self, name=None, max_age=webapp_config.DEFAULT_VALUE,
                    factory=SecureCookieSessionFactory):
        """Returns a session for a given name. If the session doesn't exist, a
        new session is returned.

        :param name:
            Cookie name. If not provided, uses the ``cookie_name``
            value configured for this module.
        :returns:
            A dictionary-like session object.
        """
        name = name or self.config['cookie_name']

        if max_age is webapp_config.DEFAULT_VALUE:
            max_age = self.config['session_max_age']

        container = self._get_session_container(name, factory)
        return container.get_session(max_age=max_age)

    # Signed cookies ----------------------------------------------------------

    def get_secure_cookie(self, name, max_age=webapp_config.DEFAULT_VALUE):
        """Returns a deserialized secure cookie value.

        :param name:
            Cookie name.
        :param max_age:
            Maximum age in seconds for a valid cookie. If the cookie is older
            than this, returns None.
        :returns:
            A secure cookie value or None if it is not set.
        """
        if max_age is webapp_config.DEFAULT_VALUE:
            max_age = self.config['session_max_age']

        value = self.request.cookies.get(name)
        if value:
            return self.serializer.deserialize(name, value, max_age=max_age)

    def set_secure_cookie(self, name, value, **kwargs):
        """Sets a secure cookie to be saved.

        :param name:
            Cookie name.
        :param value:
            Cookie value. Must be a dictionary.
        :param kwargs:
            Options to save the cookie. See :meth:`get_session`.
        """
        container = self._get_session_container(name,
                                                SecureCookieSessionFactory)
        container.session = value
        container.session_args.update(kwargs)

    # Saving to a response object ---------------------------------------------

    def save_sessions(self, response):
        """Saves all cookies and sessions to a response object.

        :param response:
            A :class:`webapp.Response` object.
        """
        for session in self.sessions.values():
            session.save_session(response)

    def save_secure_cookie(self, response, name, value, **kwargs):
        value = self.serializer.serialize(name, value)
        response.set_cookie(name, value, **kwargs)
