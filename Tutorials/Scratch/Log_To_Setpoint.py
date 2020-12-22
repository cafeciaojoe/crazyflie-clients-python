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
from cflib.crazyflie.log import LogConfig

# URI to the Crazyflie to connect to
uri =   'radio://0/80/2M/E7E7E7E7E7'
uri_2 = 'radio://0/80/2M/E7E7E7E7ED'


position_estimate = [0, 0, 0]

def log_pos_callback(timestamp, data, logconf):
    print(data)
    global position_estimate
    position_estimate[0] = data['stateEstimate.x']
    position_estimate[1] = data['stateEstimate.y']
    position_estimate[2] = data['stateEstimate.z']

def simple_sequence():
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        with PositionHlCommander(scf) as pc:
            pc.forward(1.0)
            pc.left(1.0)
            pc.back(1.0)
            pc.go_to(0.0, 0.0, 1.0)



if __name__ == '__main__':
    cflib.crtp.init_drivers(enable_debug_driver=False)

    with SyncCrazyflie(uri_2, cf=Crazyflie(rw_cache='./cache')) as scf:
        logconf = LogConfig(name='Position', period_in_ms=10)
        logconf.add_variable('stateEstimate.x', 'float')
        logconf.add_variable('stateEstimate.y', 'float')
        logconf.add_variable('stateEstimate.z', 'float')
        scf.cf.log.add_config(logconf)
        logconf.data_received_cb.add_callback(log_pos_callback)

        logconf.start()

        with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:

            simple_sequence()

        logconf.stop()

