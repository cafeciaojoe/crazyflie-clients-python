import time
import math
import threading
import random
# import logging
# import cflib.crtp
# from cflib.crazyflie import Crazyflie
# from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
# from cflib.crazyflie.log import LogConfig
# from cflib.crazyflie.syncLogger import SyncLogger



# URI to the Crazyflie to connect to
# uri = 'radio://0/80/2M/E7E7E7E7E7'

# logging.basicConfig(level=logging.ERROR)

class HTTYD():

    def __init__(self):
        self.valid_cf_pos = Position(0, 0, 0)
        self.cf_pos = Position(0, 0, 0)
        self._event = threading.Event()

    def flight_controller(self):
        lost_tracking_threshold = 100
        frames_without_tracking = 0
        while True:
            # print('start of main control loop')

            if self.cf_pos.is_valid():
                self.valid_cf_pos = self.cf_pos
                print('valid cf pos is {}'.format(self.valid_cf_pos))
                frames_without_tracking = 0
            else:
                # if it isn't, count number of frames
                frames_without_tracking += 1
                print('frames without tracking {}'.format(frames_without_tracking))

                if frames_without_tracking > lost_tracking_threshold:
                    # self.switch_flight_mode(FlightModeStates.GROUNDED)
                    print("Tracking lost, turning off motors")
                    # logger.info(self.status)

            # # If the cf is upside down, kill the motors
            # if self.flight_mode != FlightModeStates.GROUNDED and (
            #         self.valid_cf_pos.roll > 120
            #         or self.valid_cf_pos.roll < -120):
            #     self.switch_flight_mode(FlightModeStates.GROUNDED)
            #     self.status = "Status: Upside down, turning off motors"
            #     logger.info(self.status)

            # Switch on the FlightModeState and take actions accordingly
            # Wait so that any on state change actions are completed
            self._event.wait()
            print('start the ifelif statements')
            time.sleep(.5)


    def flight_logger(self):

        print('start of the flight_logger')

        rawAngle0x = [0, 0]

        state_estimate = [0, 0, 0]


        for i in range(100):
            print(i,'')
            if i % 2 == 0:
                print('updating raw angles')
                rawAngle0x.append(random.randint(1,4))
                rawAngle0x.pop(0)
                print(rawAngle0x)
                if rawAngle0x[0] == rawAngle0x[1]:
                    print('values are none')
                    print(rawAngle0x[0], rawAngle0x[1])
                    self.cf_pos = Position(float('nan'),float('nan'),float('nan'),)
                    print(self.cf_pos.x, self.cf_pos.y, self.cf_pos.z)
                    time.sleep(1)
                    self._event.set()

            if i % 2 != 0:
                print(rawAngle0x[0], rawAngle0x[1])
                if rawAngle0x[0] != rawAngle0x[1]:
                    print('updating state estimate')
                    state_estimate[0] = random.randint(10,15)
                    state_estimate[1] = random.randint(10,15)
                    state_estimate[2] = random.randint(10,15)
                    self.cf_pos = Position(state_estimate[0], state_estimate[1], state_estimate[2])
                    print(self.cf_pos)
                    time.sleep(1)
                    self._event.set()

    def main(self):

        t1 = threading.Thread(target=self.flight_controller)
        t2 = threading.Thread(target=self.flight_logger)

        t1.start()
        t2.start()



class Position:
    def __init__(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0):
        self.x = x
        self.y = y
        self.z = z
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw

    def distance_to(self, other_point):
        return math.sqrt(
            math.pow(self.x - other_point.x, 2) +
            math.pow(self.y - other_point.y, 2) +
            math.pow(self.z - other_point.z, 2))

    def is_valid(self):
        # Checking if the respective values are nan
        # if any of them were nan then the function returns false
        print('is valid has run')
        return self.x == self.x and self.y == self.y and self.z == self.z
        # if not self.x:
        #     return False
        # else:
        #     return True

    def __str__(self):
        return "x: {} y: {} z: {} Roll: {} Pitch: {} Yaw: {}".format(
            self.x, self.y, self.z, self.roll, self.pitch, self.yaw)

if __name__ == '__main__':

    s = HTTYD()

    s.main()
