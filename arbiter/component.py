# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import logging

from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

log = logging.getLogger(__name__)

class Component:
    def __init__(self, parent):
        """Configure component"""

    def run(self):
        """Run component logic in gevent-thread"""

class WSGIComponent(Component):
    """A component that starts an WSGI application"""
    bind = ":8080"
    ws = False
    app = None

    def run(self):
        host, port = self.bind.split(":")
        log.info("Starting server for %r on %r", self.app, self.bind)
        kwargs = {}
        if self.ws:
            def app(environ, start_response):
                path = environ["PATH_INFO"]
                handler = self.ws.get(path)
                if handler and "wsgi.websocket" in environ:
                    return handler(self, environ["wsgi.websocket"])
                return self.app(environ, start_response)
            kwargs = {"handler_class": WebSocketHandler}
            logging.getLogger("geventwebsocket.handler").setLevel(logging.INFO)
        else:
            app = self.app
        server = WSGIServer((host, int(port)), app, **kwargs)
        server.serve_forever()
