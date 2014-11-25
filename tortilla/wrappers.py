# -*- coding: utf-8 -*-

import os
import time

import bunch
import colorclass
import requests

from .compat import string_type, to_unicode


debug_messages = {
    'request': (
        '{blue}Executing {method} request:{/blue}\n'
        '{hiblack}'
        '    URL:   {url}\n'
        '    headers: {headers}\n'
        '    query: {params}\n'
        '    data:  {data}\n'
        '{/hiblack}'
    ),
    'success_response': (
        '{green}Got {status_code} {reason}:{/green}\n'
        '{hiblack}'
        '    {text}\n'
        '{/hiblack}'
    ),
    'failure_response': (
        '{red}Got {status_code} {reason}:{/red}\n'
        '{hiblack}'
        '    {text}\n'
        '{/hiblack}'
    ),
    'cached_response': (
        '{cyan}Cached response:{/cyan}\n'
        '{hiblack}'
        '    {text}\n'
        '{/hiblack}'
    ),
}


if os.name == 'nt':
    colorclass.Windows.enable()


class Client(object):
    """Wrapper around the most basic methods of the requests library."""

    def __init__(self, debug=False):
        self.headers = bunch.Bunch()
        self.debug = debug
        self.cache = {}

    def _log(self, message, debug=None, **kwargs):
        """Outputs a colored and formatted message in the console
        if the debug mode is activated.

        :param message: the message that will be printed
        :param debug: (optional) Overwrite of `Client.debug`
        :param kwargs: (optional) Arguments that will be passed
            to the `str.format()` method
        """
        display_log = self.debug
        if debug is not None:
            display_log = debug
        if display_log:
            colored_message = colorclass.Color(message)
            print((colored_message.format(**kwargs)))

    def request(self, method, url, path=(), params=None, headers=None,
                data=None, debug=None, cache_lifetime=None, **kwargs):
        """Requests a URL and returns a *Bunched* response.

        This method basically wraps the request method of the requests
        module and adds a `path` and `debug` option.

        A `ValueError` will be thrown if the response is not JSON encoded.

        :param method: The request method, e.g. 'get', 'post', etc.
        :param url: The URL to request
        :param path: (optional) Appended to the request URL. This can be
            either a string or a list which will be joined
            by forward slashes.
        :param params: (optional) The URL query parameters
        :param headers: (optional) Extra headers to sent with the request.
            Existing header keys can be overwritten.
        :param data: (optional) Dictionary
        :param debug: (optional) Overwrite of `Client.debug`
        :param kwargs: (optional) Arguments that will be passed to
            the `requests.request` method
        :return: :class:`Bunch` object from JSON-parsed response
        """

        if not isinstance(path, string_type):
            path = '/'.join(path)

        request_headers = dict(self.headers.__dict__)
        if headers is not None:
            request_headers.update(headers)

        if debug is None:
            debug = self.debug

        url = url + path

        self._log(debug_messages['request'], debug,
                  method=method.upper(), url=url, headers=request_headers,
                  params=params, data=data)

        cache_key = (url, str(params), str(headers))
        if cache_key in self.cache:
            item = self.cache[cache_key]
            if item['expires'] > time.time():
                self._log(debug_messages['cached_response'], debug,
                          text=item['value'])
                return bunch.bunchify(item['value'])
            del self.cache[cache_key]

        r = requests.request(method, url, params=params,
                             headers=request_headers, data=data, **kwargs)

        json_response = r.json()

        if cache_lifetime > 0 and method.lower() == 'get':
            self.cache[cache_key] = {'expires': time.time() + cache_lifetime,
                                     'value': json_response}

        debug_message = 'success_response' if r.status_code == 200 else \
            'failure_response'
        self._log(debug_messages[debug_message], debug,
                  status_code=r.status_code, reason=r.reason,
                  text=json_response)

        return bunch.bunchify(json_response)


class Wrap(object):
    """Represents a part of the wrapped URL.

    You can chain this object to other Wrap objects. This is done
    *automagically* when accessing non-existing attributes of the object.

    The root of the chain should be a :class:`Client` object. When a new
    :class:`Wrap` object is created without a parent, it will create a
    new :class:`Client` object which will act as the root.
    """

    def __init__(self, part, parent=None, headers=None, debug=None,
                 cache_lifetime=None):
        self.part = part
        self._parts = None
        self.parent = parent or Client(debug=debug)
        self.headers = bunch.bunchify(headers) if headers else bunch.Bunch()
        self.debug = debug
        self.cache_lifetime = cache_lifetime

    def parts(self):
        if self._parts:
            return self._parts
        try:
            self._parts = '/'.join([self.parent.parts(), self.part])
        except AttributeError:
            self._parts = self.part
        return self._parts

    def __call__(self, part=None, **options):
        """Creates and returns a new :class:`Wrap` object in the chain
        if `part` is provided. If not, the current object's options
        will be manipulated by the provided `options` ``dict`` and the
        current object will be returned.

        Usage::

            # creates a new Wrap, assuming `foo` is already wrapped
            foo('bar')

            # this is the same as:
            foo.bar()

            # which is the same as:
            foo.bar

            # enabling `debug` for a specific chain object
            foo.bar(debug=True)

        :param part: (optional) The URL part to append to the current chain
        :param options: (optional) Arguments accepted by the
            :class:`Wrap` initializer
        """
        if not part:
            self.__dict__.update(**options)
            return self
        try:
            return self.__dict__[part]
        except KeyError:
            self.__dict__[part] = Wrap(part=part, parent=self,
                                       debug=self.debug, **options)
            return self.__dict__[part]

    def __getattr__(self, part):
        try:
            return self.__dict__[part]
        except KeyError:
            self.__dict__[part] = Wrap(part=part, parent=self,
                                       debug=self.debug)
            return self.__dict__[part]

    def request(self, method, pk=None, **options):
        """Requests a URL and returns a *Bunched* response.

        This method basically wraps the request method of the requests
        module and adds a `path` and `debug` option.

        :param method: The request method, e.g. 'get', 'post', etc.
        :param pk: (optional) A primary key to append to the path
        :param url: (optional) The URL to request
        :param path: (optional) Appended to the request URL. This can be
            either a string or a list which will be joined
            by forward slashes.
        :param params: (optional) The URL query parameters
        :param headers: (optional) Extra headers to sent with the request.
            Existing header keys can be overwritten.
        :param data: (optional) Dictionary
        :param debug: (optional) Overwrite of `Client.debug`
        :param kwargs: (optional) Arguments that will be passed to
            the `requests.request` method
        :return: :class:`Bunch` object from JSON-parsed response
        """

        if not options.get('url'):
            # if a primary key is given, it is joined with the requested URL
            if pk:
                options['url'] = '/'.join([self.parts(), to_unicode(pk)])
            else:
                options['url'] = self.parts()

        if self.debug is not None:
            options.setdefault('debug', self.debug)
        if self.cache_lifetime is not None:
            options.setdefault('cache_lifetime', self.cache_lifetime)

        # headers are copied into a new object so temporary
        # custom headers aren't overriding future requests
        headers = self.headers.copy()
        if options.get('headers'):
            headers.update(options['headers'])
        options['headers'] = headers

        return self.parent.request(method=method, **options)

    def get(self, pk=None, **options):
        """Executes a `GET` request on the currently formed URL."""
        return self.request('get', pk, **options)

    def post(self, pk=None, **options):
        """Executes a `POST` request on the currently formed URL."""
        return self.request('post', pk, **options)

    def put(self, pk=None, **options):
        """Executes a `PUT` request on the currently formed URL."""
        return self.request('put', pk, **options)

    def patch(self, pk=None, **options):
        """Executes a `PATCH` request on the currently formed URL."""
        return self.request('patch', pk, **options)

    def delete(self, pk=None, **options):
        """Executes a `DELETE` request on the currently formed URL."""
        return self.request('delete', pk, **options)

    def __repr__(self):
        return "<{} for {}>".format(self.__class__.__name__, self.parts())