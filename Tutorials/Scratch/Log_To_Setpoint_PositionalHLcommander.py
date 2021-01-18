import logging
import time

"""The cflib.crtp module is for scanning for Crazyflies instances."""
import cflib.crtp

"""The Crazyflie class is used to easily connect/send/receive data from a Crazyflie."""
from cflib.crazyflie import Crazyflie

""" The synCrazyflie class is a wrapper around the “normal” Crazyflie class. It handles the asynchronous nature of the 
Crazyflie API and turns it into blocking function. """
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

from cflib.positioning.position_hl_commander import PositionHlCommander
from cflib.crazyflie import HighLevelCommander

from cflib.crazyflie.log import LogConfig

# URI to the Crazyflie to connect to
uri =   'radio://0/80/2M/E7E7E7E7E7'
uri_2 = 'radio://0/80/2M/E7E7E7E7ED'
uri_3 = 'radio://0/80/2M/A0A0A0A0AA'


position_estimate = [0, 0, 0, 0, 0, 0]

def log_pos_callback_L(timestamp, data, logconf):
    # print(data)
    global position_estimate
    position_estimate[0] = data['stateEstimate.x']
    position_estimate[1] = data['stateEstimate.y']
    position_estimate[2] = data['stateEstimate.z']

def log_pos_callback_R(timestamp, data, logconf):
    # print(data)
    global position_estimate
    position_estimate[3] = data['stateEstimate.x']
    position_estimate[4] = data['stateEstimate.y']
    position_estimate[5] = data['stateEstimate.z']

def follow():
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        with PositionHlCommander(scf) as pc:
            velocity = 2
            pc.set_default_velocity(velocity)
            yaw = 0
            while True:
                # pc.go_to(0,0,.6)
                # time.sleep(8)
                # pc.go_to(0, 0, 1.16)
                # time.sleep(8)
                # pc.go_to(0, 0, 1.6)
                # time.sleep(8)
                # pc.go_to(0, 0, 2.1)
                # time.sleep(8)

                # pc.go_to(-.2, 0, 1)
                # time.sleep(1)
                # pc.go_to(1, 0, 1)
                # time.sleep(1)
                # # velocity += .1

                set_point_x = (position_estimate[0] + position_estimate[3]) / 2
                set_point_y = (position_estimate[1] + position_estimate[4]) / 2
                set_point_z = (position_estimate[2] + position_estimate[5]) / 2
                if set_point_z < 0.2:
                    set_point_z = 0.2
                    yaw = 0
                elif 0.2 < set_point_z < 1.6:
                    yaw = (set_point_z/1.6)*(6.28319)
                else:
                    set_point_z = 1.6
                    yaw = 6.28319

                pc.go_to(set_point_x, set_point_y, set_point_z,yaw)
                print(round(set_point_x,2), round(set_point_y,2), round(set_point_z,2))

                time.sleep(0.1)


if __name__ == '__main__':
    cflib.crtp.init_drivers(enable_debug_driver=False)

    with SyncCrazyflie(uri_2, cf=Crazyflie(rw_cache='./cache')) as scf_2:
        logconf_2 = LogConfig(name='Position', period_in_ms=10)
        logconf_2.add_variable('stateEstimate.x', 'float')
        logconf_2.add_variable('stateEstimate.y', 'float')
        logconf_2.add_variable('stateEstimate.z', 'float')
        scf_2.cf.log.add_config(logconf_2)
        logconf_2.data_received_cb.add_callback(log_pos_callback_L)

        with SyncCrazyflie(uri_3, cf=Crazyflie(rw_cache='./cache')) as scf_3:
            logconf_3 = LogConfig(name='Position', period_in_ms=10)
            logconf_3.add_variable('stateEstimate.x', 'float')
            logconf_3.add_variable('stateEstimate.y', 'float')
            logconf_3.add_variable('stateEstimate.z', 'float')
            scf_3.cf.log.add_config(logconf_3)
            logconf_3.data_received_cb.add_callback(log_pos_callback_R)

            logconf_2.start()
            logconf_3.start()
            follow()


