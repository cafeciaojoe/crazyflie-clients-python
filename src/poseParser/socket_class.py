"""
This class is derived from my older code and has been modified to suit this assignment.
-Nick Huppert, s3729119

Essentially, this class is designed to handle the sending/receiving/listening portion
of messaging over sockets. It can act as both a server (receiver) or a client (sender)
and is mainly used to simplify the logic of using messages and make made code look neater.
If run as a server (which is the default) it will call the function got_message() in the
class that created it whenever a message is received.
When creating an instance of this class, the callback generally should be set to "self" eg:
socket_manager = SocketManager(self, port=int(port))
"""

import sys
import socket
import threading
from time import sleep
import pickle

class SocketManager:
    """
    Warnings:
        Requires implementing classes to define a callback class that implements a
        "got_message(self, address, message)" function.
    """
    DEFAULT_IP = "127.0.0.1"
    DEFAULT_PORT = 5001
    DEFAULT_PACKET_SIZE = 4096
    DEFAULT_IDLE_TIMEOUT = 3
    run = True

    def __init__(self, callback, ip=DEFAULT_IP, port=DEFAULT_PORT, packet_size=DEFAULT_PACKET_SIZE,
                 timeout=DEFAULT_IDLE_TIMEOUT, server=True):
        self.__host_ip = ip
        self.__host_port = port
        self.__packet_size = packet_size
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if server:
            self.socket.bind((self.__host_ip, self.__host_port))
        self.__timeout = timeout
        self.callback = callback

    def listen(self):
        """
        Starts the socket server listening for connections in new thread.
        Each connection is dispatched to a new thread.
        """
        SocketManager.run = True
        self.socket.listen()
        threading.Thread(target=self.__listen_loop).start()
        print("Now listening on port: %s" % self.__host_port)

    def __listen_loop(self):
        try:
            while SocketManager.run is True:
                self.socket.settimeout(self.__timeout)
                try:
                    client, address = self.socket.accept()
                    client.settimeout(self.__timeout)
                    threading.Thread(target=self.__server_action, args=(client, address)).start()
                except socket.timeout:
                    pass
        except threading.ThreadError:
            pass
        except SystemExit:
            self.stop_server()
        finally:
            self.socket.close()

    # Parse the message received from a client and call appropriate function
    def __server_action(self, client, address):
        """
        Args:
            client: The client who has connected to the server
            address: The address of the client
        """
        response = ""
        try:
            with client:
                while True:
                    message = client.recv(self.__packet_size)
                    if message == b'':
                        break
                    if message is not None:
                        response = str(self.callback.got_message(address, pickle.loads(message)))
                        client.sendall(pickle.dumps(response))
                        break
                    else:
                        break

        except (TimeoutError, AttributeError, socket.timeout, ConnectionError, ConnectionRefusedError) as e:
            print("%s" % e)
        finally:
            client.close()

    def send_message(self, ip=DEFAULT_IP, port=DEFAULT_PORT, message=None):
        """
        Takes a string message and sends it to remote server, returning the response.

        Args:
            ip(str): IP address to connect to as string.
            port(int): Port number to connect to.
            message(any): The message to send to the remote server.

        Returns:
            any: The response of the server or None on error.
         """
        socket_connection = None
        try:
            socket_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            response = None
            socket_connection.connect((ip, int(port)))
            socket_connection.sendall(pickle.dumps(message))
            sleep(.1)
            while response is None:
                response = socket_connection.recv(self.__packet_size)
            socket_connection.close()
            return pickle.loads(response)
        except (ConnectionRefusedError, AttributeError, socket.timeout, ConnectionError) as e:
            # print("%s" % e)
            return_value = "CONNECTION ERROR"
        finally:
            socket_connection.close()
        return return_value

    def stop_server(self):
        SocketManager.run = False

    def update_callback(self, new_callback):
        self.callback = new_callback

