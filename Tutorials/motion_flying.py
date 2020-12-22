import logging
import time

"""The cflib.crtp module is for scanning for Crazyflies instances."""
import cflib.crtp

"""The Crazyflie class is used to easily connect/send/receive data from a Crazyflie."""
from cflib.crazyflie import Crazyflie

""" The synCrazyflie class is a wrapper around the “normal” Crazyflie class. It handles the asynchronous nature of the 
Crazyflie API and turns it into blocking function. """
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

"""This imports the motion commander, which is pretty much a wrapper around the position setpoint frame work of the crazyflie."""
from cflib.positioning.motion_commander import MotionCommander

from cflib.crazyflie.log import LogConfig

URI = 'radio://0/80/2M/E7E7E7E7E7'
is_deck_attached = False

logging.basicConfig(level=logging.ERROR)

position_estimate = [0, 0]

DEFAULT_HEIGHT = 0.5
BOX_LIMIT = 0.25


def log_pos_callback(timestamp, data, logconf):
    print(data)
    global position_estimate
    position_estimate[0] = data['stateEstimate.x']
    position_estimate[1] = data['stateEstimate.y']

"""parameter callback function"""
def param_deck_flow(name, value):
    global is_deck_attached
    """kw global allows a global variable to be modified in the scope of this funciton"""
    print(value)
    if value:
        is_deck_attached = True
        print('Deck is attached!')
    else:
        is_deck_attached = False
        print('Deck is NOT attached!')



"""The reason for the crazyflie to immediately take off, is that the motion commander if intialized with a take
off function that will already start sending position setpoints to the crazyflie. Once the script goes out of the
instance, the motion commander instance will close with a land function.
creating and instance with 'with' will invoke the __enter__ method (which will launch the cf)
leaving an instance will invoke the __exit__ method, (which will land the cf)
"""


def take_off_simple(scf):
    with MotionCommander(scf, default_height = DEFAULT_HEIGHT) as mc:
        time.sleep(3)


def move_linear_simple(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)
        mc.turn_left(180)
        time.sleep(1)
        mc.forward(0.5)
        time.sleep(1)


def move_box_limit(scf):
    with MotionCommander(scf, default_height=DEFAULT_HEIGHT) as mc:
        body_x_cmd = 0.2;
        body_y_cmd = 0.1;
        max_vel = 0.2;

        while (1):
            if position_estimate[0] > BOX_LIMIT:
                 body_x_cmd=-max_vel
            elif position_estimate[0] < -BOX_LIMIT:
                body_x_cmd=max_vel
            if position_estimate[1] > BOX_LIMIT:
                body_y_cmd=-max_vel
            elif position_estimate[1] < -BOX_LIMIT:
                body_y_cmd=max_vel

            mc.start_linear_motion(body_x_cmd, body_y_cmd, 0)

            time.sleep(0.1)



if __name__ == '__main__':


    """Initialize the low-level drivers (don't list the debug drivers)"""
    cflib.crtp.init_drivers(enable_debug_driver=False)

    """with an instance of SyncCrazyflie as scf do these things."""
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:

        """We want to know if the flow deck is correctly attached before flying, therefore we will add a callback for the "deck.bcFlow2" parameter. """
        scf.cf.param.add_update_callback(group="deck", name="bcFlow2",
                                cb=param_deck_flow)
        time.sleep(1)

        """Here you will add the log variables you would like to read out. If you are unsure how your variable is called,
             this can be checked by connecting to Crazyflie to the cfclient and look at the log TOC tab. If the variables don’t
            match, you get a KeyError """

        logconf = LogConfig(name='Position', period_in_ms=10)
        logconf.add_variable('stateEstimate.x', 'float')
        logconf.add_variable('stateEstimate.y', 'float')
        scf.cf.log.add_config(logconf)
        logconf.data_received_cb.add_callback(log_pos_callback)

        if is_deck_attached:
            logconf.start()

            move_box_limit(scf)

            logconf.stop()