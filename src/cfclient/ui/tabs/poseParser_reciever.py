from poseParser.socket_class import SocketManager

class main:

    def __init__(self, *args):
        print("hey")
        self.server = SocketManager(self, server = True, port=5050)
        self.server.listen()



    def got_message(self, address,data):
        # address is given but not used
        # Send the data to where you want it from here
        print(data)


        pass

if __name__ == "__main__":
    main()