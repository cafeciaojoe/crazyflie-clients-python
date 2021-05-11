from poseParser.socket_class import SocketManager
import time

class main:

    def __init__(self, *args):
        print("hey")
        self.server = SocketManager(self, server = True, port=5050)
        self.server.listen()
        self.server.send_message(message = {'username':'test_user'})
        print('username sent')
        self.start_follow_mode()


    def got_message(self, address,data):
        # address is given but not used
        # Send the data to where you want it from here
        print(data)
        pass

    def start_follow_mode(self):
        print('sending follow mode mode over socket')
        self.server.send_message(message={"flightmode": 'follow'})
        time.sleep(20)
        self.stop_follow_mode()

    def stop_follow_mode(self):
        print('sending not follow over socket')
        self.server.send_message(message={"flightmode": 'not follow'})


if __name__ == "__main__":
    main()