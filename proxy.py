#!/usr/bin/env python

import socket, sys, threading, os
from httplib import HTTPResponse
from BaseHTTPServer import BaseHTTPRequestHandler
from StringIO import StringIO

serverAddr = '127.0.0.1'
debug = 0
verbose = 1
verbose2 = 0

class FakeSocket():
    def __init__(self, response_str):
        self._file = StringIO(response_str)
    def makefile(self, *args, **kwargs):
        return self._file

class HTTPRequest(BaseHTTPRequestHandler):
    def __init__(self, request_text):
        self.rfile = StringIO(request_text)
        self.raw_requestline = self.rfile.readline()
        self.error_code = self.error_message = None
        self.parse_request()

    def send_error(self, code, message):
        self.error_code = code
        self.error_message = message

class TheServer:
    
    maxCon = 500 # backlog for the sever
    active_cons = {} # dictionary for active connections
    cache = {} # cache data for faster reply
    buffer_size = 4096 # set buffer size to 4 KB
    timeout = 200 #set timeout to 2 seconds

    def __init__(self, host, port):

        """ Initialise the server """

        try:
            self.port = port
            self.address = host
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((host, port))
            self.server.listen(self.maxCon)
            print("Proxy Server started successfully. Listening on port: " + str(port) + "\n")
        except Exception as e:
            print("Error => Could not bind socket: " + str(e))
            print("Exiting application...")
            self.shutdown()

    def main_loop(self):

        """ Listen for incoming connections """
        
        print("Listening for incoming connections...\n")
        while 1:

            # Establish the connection
            try:
                clientSocket, client_address = self.server.accept()
            except Exception as e:
                print("Error on accepting connection from client: " + str(e))
                continue
            print("\nAccepted connection from " + ':'.join(str(i) for i in client_address))

            self.active_cons.update({clientSocket : client_address})
            
            d = threading.Thread(name = client_address[0],
                target = self.proxy_thread, args=(clientSocket,))
            d.setDaemon(True)
            d.start()

    def close_client(self, conn):
        lk = threading.Lock()
        lk.acquire()
        client_info = self.active_cons.pop(conn)
        lk.release()
        conn.close()

    def parse_request(self, request):

        """ Parse request from cient """

        try:
            req = HTTPRequest(request)
            if req.command == 'CONNECT':
                print("Unsupported request type. Currently this proxy server doesn't handles CONNECT requests :(")
                return (0, 0, 0, 0)
            if 'host' in req.headers:
                remote_host = req.headers['host']
            else:
                remote_host = None
            if req.path.startswith('http'):
                if remote_host is None:
                    remote_host = req.path.replace('http://', '').split(':')[0].strip('/')
                cachekey = req.command + ':' + req.path.strip('/')
                try:
                    remote_port = int(requrl.split(':')[2])
                except:
                    remote_port = 80
            else:
                if remote_host is None and req.path.startswith('/'):
                    print("Invalid request!!")
                    return(0, 0, 0, 0)
                else:
                    remote_host = req.path.split(':')[0].strip('/')
                cachekey = req.command + ':' + 'http://' + remote_host + req.path.strip('/')
                try:
                    remote_port = int(requrl.split(':')[1])
                except:
                    remote_port = 80
        except Exception as e:
            print("Error in parsing request: " + str(e))
            return(0, 0, 0, 0)
        """
        method, requrl, httpversion = request.split('\n')[0].split(' ')
        remote_host = request.split('\n')[1].split(':')[1].strip()

        #remote_host = requrl.replace('http://', '').strip('/').split(':')[0]
        #print("Req host: " + remote_host)
        try:
            remote_port = int(requrl.split(':')[1])
        except:
            remote_port = 80
        cachekey = method + ':' + remote_host + ':' + str(remote_port)"""
        return (remote_host, remote_port, cachekey, 1)

    def proxy_check(self, remote_host):
        if os.environ['http_proxy'] == '' or remote_host.endswith('.iiit.ac.in') or remote_host == 'localhost':
            return False
        return True

    def proxy_thread(self, conn):

        """ Thread to handle requests from client/browser """

        curr_client = ':'.join(str(i) for i in self.active_cons[conn])
        print("Started new thread for " + curr_client)
                
        try:
            request = conn.recv(self.buffer_size) # get request from client
        except Exception as e:
            print("Error in receiving request from the client: " + curr_client + ". Closing Connection...")
            self.close_client(conn)
            return
        print("Received request:\n" + request)

        remote_host, remote_port, cachekey, valid = self.parse_request(request)
        if not valid:
            self.close_client(conn)
            return

        if cachekey in self.cache:
            # key found in cache, return data from cache
            if verbose: print("*****Cachehit*****")
            self.relay_to_client(conn, 0, cachekey, 1)
            self.close_client(conn)
            return

        if self.proxy_check(remote_host):
            proxy = os.environ['http_proxy']
            proxy_host = proxy.split('//')[1].split(':')[0]
            proxy_port = int(proxy.split(':')[2].strip('/'))
            remote_socket = self.forward_to_proxy(proxy_host, proxy_port, request)
        else:
            remote_socket = self.relay_to_remote(remote_host, remote_port, request)
        if remote_socket:
            response = self.relay_to_client(conn, remote_socket)
            if response:
                self.cache_storage(cachekey, response)
        else:
            print("Closing connection with client: " + curr_client)
        
        self.close_client(conn)


    def relay_to_remote(self, remote_host, remote_port, request):
        
        """ Relay the request from client to the remote server """

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((remote_host, remote_port))
            s.sendall(request)
            return s
        except Exception as e:
            print("Cannot relay data to the remote server: " + remote_host + ':' + str(remote_port))
            print("Error: " + str(e))
            return False

    def forward_to_proxy(self, proxy_host, proxy_port, request):

        """ Relay the request from client to the proxy server """

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((proxy_host, proxy_port))
            s.sendall(request)
            return s
        except Exception as e:
            print("Cannot relay data to the remote server: " + proxy_host + ':' + str(proxy_port))
            print("Error: " + str(e))
            return False

    def relay_to_client(self, client_sock, remote_sock, cachekey = '', cache = 0):
        
        """ Relay the response from remote server to the client """
        
        global verbose
        data = ''
        if cache:
            if verbose: print("relaying from cache, cachekey: " + cachekey)
            client_sock.send(self.cache[cachekey])
            return True
        
        try:
            data = remote_sock.recv(self.buffer_size)
        except Exception as e:
            print("Error in receving response from the remote server. " + str(e))
            return False
        d = data
        while len(d) > 0:
            if(debug): print("Relaying data ot client: " + d)
            client_sock.send(d)
            try:
                d = remote_sock.recv(self.buffer_size)
            except Exception as e:
                print("Error in receving response from the remote server. " + str(e))
                return False
            if (len(d) <= 0):
                break
            data += d
        return data

    def parse_response(self, response):
        
        """ Check if the response is valid to stored in cache """

        global verbose2
        try:
            source = FakeSocket(response)
            parsed_response = HTTPResponse(source)
            parsed_response.begin()
        except Exception as e:
            print("Error in parsing response. " + str(e))
            return 0
        sc = parsed_response.status # status-code
        try:
            cc = parsed_response.getheader("Cache-Control").split(',') # cache-control
        except:
            cc = []
        pragma = parsed_response.getheader("Pragma")
        if verbose2: print("sc: " + str(sc) + ", pragma: " + str(pragma) + ", cache-control: " + str(';'.join(cc)))
        if sc == 302 or sc == 301 or sc == 200 or sc == 304:
            if 'no-cache' in cc or 'private' in cc or 'no-store' in cc or pragma == 'no-cache':
                return 0
            else:
                return 1
        else:
            return 0

    def cache_storage(self, cachekey, response):

        """ Store the response in cache """

        global verbose
        if self.parse_response(response):
            lk = threading.Lock()
            lk.acquire()
            try:
                if verbose: print("adding to cache, cachekey: " + cachekey)
                self.cache.update({cachekey : response})
                #self.cache.update({cachekey : response + "\n\n***Serving from cache***\n\n"})
            finally:
                lk.release()
        else:
            if verbose: print("Cachekey: " + cachekey + ". Not adding to cache.")

    def shutdown(self):
        
        """ Clear all data from the server """

        for i in self.active_cons:
            i.close() # close all the active cons with the proxy
        self.server.close() # close the proxy socket

def getPort(port):

    """ Get the port from the user """

    global serverAddr
    while 1:
        try:

            #checking if the port inputted is open
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2) # 2 Second Timeout
            result = sock.connect_ex((serverAddr, port))
            if result == 0:
                sock.close()
                return port
            print 'Port CLOSED, connect_ex returned: ' + str(result)
            port = raw_input("Enter a different port no to be used for the proxy server: ")
        
        except KeyboardInterrupt:
            print("User requested interrupt.\nExiting...")
            sys.exit(1)

def start_server():
    global serverAddr
    if len(sys.argv) != 2:
        print("Usage: proxy.py <port>")
        return False
    port = int(sys.argv[1])
    #port = getPort(int(sys.argv[1]))
    server = TheServer(serverAddr, port)
    try:
        server.main_loop()
    except KeyboardInterrupt:
        print("User requested interrupt.\nExiting...")
        server.shutdown()

if __name__ == '__main__':
    start_server()