"""Loopback servers with no reverse-DNS lookup during startup."""
from http.server import HTTPServer,ThreadingHTTPServer
from socketserver import TCPServer

class LiteralLoopback:
    def server_bind(self):
        if self.server_address[0]!='127.0.0.1':raise ValueError('LOOPBACK_REQUIRED')
        TCPServer.server_bind(self)
        self.server_name='127.0.0.1';self.server_port=self.server_address[1]

class LocalHTTPServer(LiteralLoopback,HTTPServer):pass
class LocalThreadingHTTPServer(LiteralLoopback,ThreadingHTTPServer):pass
