



import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.syncLogger import SyncLogger

# URI to the Crazyflie to connect to
uri = 'radio://0/80/2M/A0A0A0A0A1'

# Only output errors from the logging framework
logging.basicConfig(level=logging.ERROR)


def param_stab_est_callback(name, value):
    print('The crazyflie has parameter ' + name + ' set at number: ' + value)


def choose_effect(scf, groupstr, namestr):
    cf = scf.cf
    full_name = groupstr + '.' + namestr

    cf.param.add_update_callback(group=groupstr, name=namestr,
                                 cb=param_stab_est_callback)
    time.sleep(1)
    cf.param.set_value(full_name, 13
                       )
    time.sleep(1)


def simple_freq(scf, groupstr, namestr):
    cf = scf.cf
    full_name = groupstr + '.' + namestr

    cf.param.add_update_callback(group=groupstr, name=namestr,
                                 cb=param_stab_est_callback)
    time.sleep(1)
    # Light BLue
    for i in range(10000):
        cf.param.set_value(full_name, 10)
        time.sleep(.01000)
        cf.param.set_value(full_name, 0)
        time.sleep(.2000)
        cf.param.set_value(full_name, 7)
        time.sleep(.1)
        cf.param.set_value(full_name, 6)
        time.sleep(.05)
    # Aqua - Tim Fist
    # for i in range(10000):
    #     cf.param.set_value(full_name, 6)
    #     time.sleep(.1000)
    #     cf.param.set_value(full_name, 7)
    #     time.sleep(.01000)
    #     cf.param.set_value(full_name, 10)
    #     time.sleep(.1000)
    # Amber
    # for i in range(10000):
    #     cf.param.set_value(full_name, 6)
    #     time.sleep(.1000)
    #     cf.param.set_value(full_name, 10)
    #     time.sleep(.1000)
    # blue - Tim Goodson
    # for i in range(10000):
    #     cf.param.set_value(full_name, 6)
    #     time.sleep(.01000)
    #     cf.param.set_value(full_name, 7)
    #     time.sleep(.01000)
    #     cf.param.set_value(full_name, 8)
    #     time.sleep(.01000)
    # green -Margot
    # for i in range(10000):
    #     cf.param.set_value(full_name, 6)
    #     time.sleep(.1000)
    #     cf.param.set_value(full_name, 8)
    #     time.sleep(.1000)
    #     cf.param.set_value(full_name, 11)
    #     time.sleep(.1000)
    # brown
    # for i in range(10000):
    #     cf.param.set_value(full_name, 12)
    #     time.sleep(.1000)
    #     cf.param.set_value(full_name, 6)
    #     time.sleep(.1000)
    #     cf.param.set_value(full_name, 19)
    #     time.sleep(.1000)
    for i in range(6,50):
        cf.param.set_value(full_name, i)
        time.sleep(.25)


    # for j in range(100,500,100):
    #     for i in range(50,j,1):
    #         cf.param.set_value(full_name, i)
    #         time.sleep(.001)
    #     time.sleep(1)

def log_stab_callback(timestamp, data, logconf):
    ...
def simple_log_async(scf, logconf):
    ...
def simple_log(scf, logconf):
    ...
def simple_connect():
    ...

if __name__ == '__main__':
    # Initialize the low-level drivers
    cflib.crtp.init_drivers()

    lg_stab = LogConfig(name='Stabilizer', period_in_ms=10)
    lg_stab.add_variable('stabilizer.roll', 'float')
    lg_stab.add_variable('stabilizer.pitch', 'float')
    lg_stab.add_variable('stabilizer.yaw', 'float')

    group = 'sound'
    name = 'effect'

    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        choose_effect(scf, group, name)

        # group = 'sound'
        # name = 'freq'
        #
        # simple_freq(scf, group, name)

