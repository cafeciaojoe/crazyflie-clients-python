"""https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/user-guides/sbs_connect_log_param/"""

import time
import logging

"""The cflib.crtp module is for scanning for Crazyflies instances."""
import cflib.crtp
"""The Crazyflie class is used to easily connect/send/receive data from a Crazyflie."""
from cflib.crazyflie import Crazyflie
"""
The synCrazyflie class is a wrapper around the “normal” Crazyflie class. It handles the asynchronous nature of the 
Crazyflie API and turns it into blocking function.
"""
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

"""LogConfig class is a representation of one log configuration that enables logging from the Crazyflie"""
from cflib.crazyflie.log import LogConfig

"""The SyncLogger class provides synchronous access to log data from the Crazyflie."""
from cflib.crazyflie.syncLogger import SyncLogger

from cflib.utils.power_switch import PowerSwitch


# URI to the Crazyflie to connect to
uri = 'radio://0/80/2M/E7E7E7E7E7'
# Only output errors from the logging framework
logging.basicConfig(level=logging.ERROR)

def param_stab_est_callback(name, value):
    print('The crazyflie has parameter ' + name + ' set at number: ' + value)

def simple_param_async(scf, groupstr, namestr):
    cf = scf.cf
    full_name = groupstr + "." + namestr

    cf.param.add_update_callback(group=groupstr, name=namestr,
                                           cb=param_stab_est_callback)
    time.sleep(1)

    cf.param.set_value(full_name, 2)
    time.sleep(1)

    cf.param.set_value(full_name, 1)
    time.sleep(1)


def log_stab_callback(timestamp, data, logconf):
    print('[%d][%s]: %s' % (timestamp, logconf.name, data))


"""Here you add the logging configuration to to the logging framework of the Crazyflie. 
It will check if the log configuration is part of the TOC, which is a list of all the logging 
variables defined in the Crazyflie. You can test this out by changing one of the lg_stab variables 
to a completely bogus name like 'not.real'. In this case you would receive the following message:

KeyError: 'Variable not.real not in TOC'"""
def simple_log_async(scf, logconf):
    cf = scf.cf
    cf.log.add_config(logconf)

    # """This callback will be called once the log variables have received it and prints the contents.
    #  The callback function added to the logging framework by adding it to the log config in simple_log_async(..):"""
    logconf.data_received_cb.add_callback(log_stab_callback)

    # """Then the log configuration would need to be started manually, and then stopped after a few seconds:"""
    logconf.start()
    while True:
        a = 1

    logconf.stop()

def simple_log(scf, logconf):

    """
    With an instance of synclogger(args, args) going by the name logger:
    do this,
    .
    """
    with SyncLogger(scf, lg_stab) as logger:

        for log_entry in logger:

            timestamp = log_entry[0]
            data = log_entry[1]
            logconf_name = log_entry[2]

            print('[%d][%s]: %s' % (timestamp, logconf_name, data))

            # break


def simple_connect(uri):

    print("yeah, I'm connected up!")
    PowerSwitch(uri).stm_power_cycle()
    time.sleep(20)
    print("now I will disconnect")


if __name__ == '__main__':
    # Initialize the low-level drivers (don't list the debug drivers)
    cflib.crtp.init_drivers(enable_debug_driver=False)

    """Here you will add the log variables you would like to read out. If you are unsure how your variable is called,
     this can be checked by connecting to Crazyflie to the cfclient and look at the log TOC tab. If the variables don’t
    match, you get a KeyError (more on that later.)"""
    lg_stab = LogConfig(name='lighthouse', period_in_ms=100)
    lg_stab.add_variable('lighthouse.')
    # lg_stab.add_variable('lighthouse.rawAngle0x', 'float')
    # lg_stab.add_variable('lighthouse.rawAngle0y', 'float')
    # lg_stab.add_variable('lighthouse.rawAngle1x', 'float')
    # lg_stab.add_variable('lighthouse.rawAngle1y', 'float')

    group = "stabilizer"
    name = "estimator"

    """with an instance of SyncCrazyflie as scf
    do these things. 
    """
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:

        simple_connect(uri)

        # simple_log(scf, lg_stab)

        # simple_log_async(scf, lg_stab)

        # """calling the async param read/write function on the stabilizer/estimator funciton"""
        # simple_param_async(scf, group, name)