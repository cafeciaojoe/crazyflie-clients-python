import time
import math
import threading
import logging
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger



# URI to the Crazyflie to connect to
uri = 'radio://0/80/2M/E7E7E7E7E7'

logging.basicConfig(level=logging.ERROR)

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
                    self._event.wait()
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
            time.sleep(0.001)


    def flight_logger(self):

        print('start of the flight_logger')
        # Initialize the low-level drivers (don't list the debug drivers)
        cflib.crtp.init_drivers(enable_debug_driver=False)

        log_angle = LogConfig(name='lighthouse', period_in_ms=100)
        log_angle.add_variable('lighthouse.rawAngle0x', 'float')
        log_angle.add_variable('lighthouse.rawAngle0y', 'float')
        log_angle.add_variable('lighthouse.rawAngle1x', 'float')
        log_angle.add_variable('lighthouse.rawAngle1y', 'float')

        log_position = LogConfig(name='Position', period_in_ms=100)
        log_position.add_variable('stateEstimate.x', 'float')
        log_position.add_variable('stateEstimate.y', 'float')
        log_position.add_variable('stateEstimate.z', 'float')

        rawAngle0x = [0, 0]
        rawAngle0y = [0, 0]
        rawAngle1x = [0, 0]
        rawAngle1y = [0, 0]

        state_estimate = [0, 0, 0]

        with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
            with SyncLogger(scf, [log_angle, log_position]) as log:
                for log_entry in log:
                    if 'lighthouse.rawAngle0x' in log_entry[1]:
                        print('updating raw angles')
                        data_1 = log_entry[1]

                        rawAngle0x.append(data_1['lighthouse.rawAngle0x'])
                        rawAngle0x.pop(0)
                        print(rawAngle0x)
                        # print(rawAngle0x)
                        # rawAngle0y.append(data_1['lighthouse.rawAngle0y'])
                        # rawAngle0y.pop(0)
                        # rawAngle1x.append(data_1['lighthouse.rawAngle1x'])
                        # rawAngle1x.pop(0)
                        # rawAngle1y.append(data_1['lighthouse.rawAngle1y'])
                        # rawAngle1y.pop(0)

                        # if rawAngle0x[0] == rawAngle0x[1] and rawAngle0y[0] == rawAngle0y[1] and rawAngle1x[0] == \
                        #         rawAngle1x[1] and rawAngle1y[0] == rawAngle1y[1]:

                        if rawAngle0x[0] == rawAngle0x[1]:
                            print('values are none')
                            print(rawAngle0x[0], rawAngle0x[1])
                            self.cf_pos = Position(None, None, None)
                            print(self.cf_pos.x, self.cf_pos.y, self.cf_pos.z)
                            self._event.set()

                    elif 'stateEstimate.x' in log_entry[1] and self.cf_pos.x:
                        print('updating state estimate')
                        data_2 = log_entry[1]
                        print(data_2)
                        state_estimate[0] = data_2['stateEstimate.x']
                        state_estimate[1] = data_2['stateEstimate.y']
                        state_estimate[2] = data_2['stateEstimate.z']
                        self.cf_pos = Position(state_estimate[0], state_estimate[1], state_estimate[2])
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
        # print('is valid has run')
        # return self.x == self.x and self.y == self.y and self.z == self.z
        if not self.x:
            return False
        else:
            return True

    def __str__(self):
        return "x: {} y: {} z: {} Roll: {} Pitch: {} Yaw: {}".format(
            self.x, self.y, self.z, self.roll, self.pitch, self.yaw)

if __name__ == '__main__':

    s = HTTYD()

    s.main()


