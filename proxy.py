#!/usr/bin/env python

import socket, sys, threading
from bs4 import BeautifulSoup

serverAddr = '127.0.0.1'
debug = 1

class TheServer:
    
    maxCon = 500 # backlog for the sever
    active_cons = {} # dictionary for active connections
    cache = {} # cache data for faster reply
    buffer_size = 4096 # set buffer size to 4 KB
    timeout = 20 #set timeout to 2 seconds

    def __init__(self, host, port):

        """ initialise the server """

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

        """ listen for incoming connections """
        
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

        """ parse request from cient """
        method, requrl, httpversion = request.split('\n')[0].split(' ')

        remote_host = requrl.replace('http://', '').strip('/').split(':')[0]
        #print("Req host: " + remote_host)
        try:
            remote_port = int(requrl.split(':')[1])
        except:
            remote_port = 80
        cachekey = method + ':' + remote_host + ':' + str(remote_port)
        return (remote_host, remote_port, cachekey)


    def proxy_thread(self, conn):

        """ thread to handle requests from client/browser """

        curr_client = ':'.join(str(i) for i in self.active_cons[conn])
        print("Started new thread for " + curr_client)
                
        try:
            request = conn.recv(self.buffer_size) # get request from client
        except Exception as e:
            print("Error in receiving request from the client: " + curr_client + ". Closing Connection...")
            conn.close()
            return
        print("Received request:\n" + request)

        remote_host, remote_port, cachekey = self.parse_request(request)

        if cachekey in self.cache:
            # key found in cache, return data from cache
            self.relay_to_client(conn, 0, cachekey, 1)
            self.close_client(conn)
            return

        remote_socket = self.relay_to_remote(remote_host, remote_port, request)
        if remote_socket:
            response = self.relay_to_client(conn, remote_socket)
            self.cache_storage(cachekey, response)
        else:
            print("Closing connection with client: " + curr_client)
        
        self.close_client(conn)


    def relay_to_remote(self, remote_host, remote_port, request):
        
        """ relay the request from client to the remote server """

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

    def relay_to_client(self, client_sock, remote_sock, cachekey = '', cache = 0):
        
        """ relay the response from remote server to the client """
        
        global debug
        data = ''
        if cache:
            if debug: print("relaying from cache, cachekey: " + cachekey)
            client_sock.send(self.cache[cachekey])
            return True
        
        data = remote_sock.recv(self.buffer_size)
        d = data
        while len(d) > 0:
            if(debug): print("Relaying data to client: " + d)
            client_sock.send(d)
            d = remote_sock.recv(self.buffer_size)
            if (len(d) <= 0):
                break
            data += d
        return data

    def parse_response(self, response):
        
        """ Check if the response is valid to stored in cache """

        return 1

    def cache_storage(self, cachekey, response):

        """ Store the response in cache """

        global debug
        if self.parse_response(response):
            lk = threading.Lock()
            lk.acquire()
            if debug: print("adding to cache, cachekey: " + cachekey)
            self.cache.update({cachekey : response})
            #self.cache.update({cachekey : response + "\n\n***Serving from cache***\n\n"})
            lk.release()

    def shutdown(self):
        
        """ clear all data from the server """

        for i in self.active_cons:
            i.close() # close all the active cons with the proxy
        self.server.close() # close the proxy socket

def getPort(port):

    """ get the port from the user """

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