
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
#
#  Crazyflie Nano Quadcopter Client
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.

import logging
import operator
import json
import math
import statistics
import time
from collections import defaultdict
from datetime import datetime
from enum import Enum

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, pyqtSlot, pyqtProperty
from PyQt5.QtCore import QStateMachine, QState, QEvent, QTimer
from PyQt5.QtCore import QAbstractTransition
from PyQt5.QtWidgets import QMessageBox

import cfclient
from cfclient.ui.tab import Tab
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger
from cflib.crazyflie import Crazyflie

from cflib.utils.power_switch import PowerSwitch

from cfclient.utils.ui import UiUtils
from poseParser.socket_class import SocketManager

from cfclient.ui.tabs import end_of_wand

import threading

__author__ = 'Bitcraze AB'
__all__ = ['HTTYD']

logger = logging.getLogger(__name__)

HTTYD_tab_class = uic.loadUiType(cfclient.module_path +
                                 "/ui/tabs/HTTYD.ui")[0]

class FlightModeEvent(QEvent):

    def __init__(self, mode, parent=None):
        super(FlightModeEvent, self).__init__(QEvent.Type(QEvent.User + 1))
        self.mode = mode


class FlightModeTransition(QAbstractTransition):

    def __init__(self, value, parent=None):
        super(FlightModeTransition, self).__init__(parent)
        self.value = value

    def eventTest(self, event):
        if event.type() != QEvent.Type(QEvent.User + 1):
            return False

        return event.mode == self.value

    def onTransition(self, event):
        pass


class FlightModeStates(Enum):
    LAND = 0
    LIFT = 1
    FOLLOW = 2
    PATH = 3
    HOVERING = 4
    GROUNDED = 5
    DISCONNECTED = 6

class BatteryStates:
    BATTERY, CHARGING, CHARGED, LOW_POWER = list(range(4))

class HTTYD(Tab, HTTYD_tab_class):
    """Define some signals that will emit some string,
    signals a are usually sent by buttons
    these signals need to be connected to a slot/slots.
    so for example, when the CF is connected, a bunch of things
    in the GUI happen.

    https://youtu.be/GIg9ehmGJHY?t=1420
    """
    _connected_signal = pyqtSignal(str)
    _connected_signal_L = pyqtSignal(str)
    _connected_signal_R = pyqtSignal(str)

    _disconnected_signal = pyqtSignal(str)
    _disconnected_signal_L = pyqtSignal(str)
    _disconnected_signal_R = pyqtSignal(str)

    _log_data_signal = pyqtSignal(int, object, object)
    _log_data_signal_L = pyqtSignal(int, object, object)
    _log_data_signal_R = pyqtSignal(int, object, object)

    _log_error_signal = pyqtSignal(object, str)
    _log_error_signal_L = pyqtSignal(object, str)
    _log_error_signal_R = pyqtSignal(object, str)

    _param_updated_signal = pyqtSignal(str, str)
    _param_updated_signal_L = pyqtSignal(str, str)
    _param_updated_signal_R = pyqtSignal(str, str)

    cfStatusChanged = pyqtSignal(str)
    cfStatusChanged_L = pyqtSignal(str)
    cfStatusChanged_R = pyqtSignal(str)

    statusChanged = pyqtSignal(str)

    batteryUpdatedSignal = pyqtSignal(int, object, object)

    socket_manager = None

    def __init__(self, tabWidget, helper, *args):
        super(HTTYD, self).__init__(*args)
        self.setupUi(self)

        # self.server = SocketManager(self, server = True, port=5050)

        self._machine = QStateMachine()
        self._setup_states()
        self._event = threading.Event()

        self.tabName = "HTTYD"
        self.menuName = "HTTYD Tab"
        self.tabWidget = tabWidget

        #  CF instances.
        self._helper = helper
        self._helper_R = Crazyflie(rw_cache='./cache')
        self._helper_L = Crazyflie(rw_cache='./cache')

        # creates a class of the socket manager and sets it to be a server, capable of listening for connections
        # self.server.listen()

        # the above helper cf instances are only assigned to _cf_L and _cf_R after they start logging
        self._cf = None
        self._cf_L = None
        self._cf_R = None

        # self.uri gets passedin in from main.py upon connection
        self.uri_L = 'radio://0/80/2M/A0A0A0A0A0'
        self.uri_R = 'radio://0/80/2M/A0A0A0A0A1'

        # assign the label to the _cf_status_ strings
        self._cf_status = self.cfStatusLabel.text()
        self._cf_status_L = self.cfStatusLabel_L.text()
        self._cf_status_R = self.cfStatusLabel_R.text()
        self._status = self.statusLabel.text()

        # initial flight modes
        # depends on how far off the ground the cf is calibrated
        self.floor_height = -1.25
        # divides the goal pos (x) by n eg x/n, x/n-1, x/n-2... x/1
        self.lift_rate = 3

        # middle phenotype values, they get adjusted later in the set_phenotype function
        self.max_training_loops = 1000
        self.leeway = .2  # this adds a little room for the x y and z values.
        self.spin_rate = .6
        self.starting_height = 1

        self.starting_freq = 0
        self.current_freq = 0
        self.freq_counter = 0
        self.isTraining = False
        self.flying_enabled = False
        self.switch_flight_mode(FlightModeStates.DISCONNECTED)
        self.path_pos_threshold = 0.2
        self.max_training_variance = .06

        self.isUnlocked = False

        self.charging = False
        self.low_power = False

        # The position and rotation of the cf and wand obtained by the
        # lighthouse tracking, if it cant be tracked the position becomes Nan
        # cf_pos_dict is what is updated by the three async flight logger calls.
        # they need to be unpacked at the top of the flight controller loop
        self.cf_pos_dict = {'cf_pos': Position(0, 0, 0),
                            'cf_pos_L': Position(0, 0, 0),
                            'cf_pos_R': Position(0, 0, 0)}
        self.cf_pos = Position(0, 0, 0)
        self.cf_pos_L = Position(0, 0, 0)
        self.cf_pos_R = Position(0, 0, 0)

        # a dict of lists that logs the position of the hands to the drone relaitve to the
        self.diff_dict = defaultdict(list)

        self.accepted_positions = {}

        # The regular cf_pos can a times due to lost tracing become Nan,
        # this the latest known valid cf position
        self.valid_cf_pos = Position(0, 0, 0)
        self.valid_cf_pos_L = Position(0, 0, 0)
        self.valid_cf_pos_R = Position(0, 0, 0)

        self.end_of_wand_L = Position(0, 0, 0)
        self.end_of_wand_R = Position(0, 0, 0)

        self.mid_pos = Position(0, 0, 0)

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._connected_signal_L.connect(self._connected_L)
        self._connected_signal_R.connect(self._connected_R)

        self._disconnected_signal.connect(self._disconnected)
        self._disconnected_signal_L.connect(self._disconnected_L)
        self._disconnected_signal_R.connect(self._disconnected_R)

        self._log_data_signal.connect(self._log_data_received)
        self._log_data_signal_L.connect(self._log_data_received_L)
        self._log_data_signal_R.connect(self._log_data_received_R)

        self._param_updated_signal.connect(self._param_updated)
        self._param_updated_signal_L.connect(self._param_updated_L)
        self._param_updated_signal_R.connect(self._param_updated_R)

        # connect the status change signals to the update status
        self.cfStatusChanged.connect(self._update_cf_status)
        self.cfStatusChanged_L.connect(self._update_cf_status_L)
        self.cfStatusChanged_R.connect(self._update_cf_status_R)

        self.statusChanged.connect(self._update_status)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(self._connected_signal.emit)
        self._helper_L.connected.add_callback(self._connected_signal_L.emit)
        self._helper_R.connected.add_callback(self._connected_signal_R.emit)

        self._helper.cf.disconnected.add_callback(self._disconnected_signal.emit)
        self._helper_L.disconnected.add_callback(self._disconnected_signal_L.emit)
        self._helper_R.disconnected.add_callback(self._disconnected_signal_R.emit)

        # Connect the UI elements
        self.liftButton.clicked.connect(self.set_lift_mode)
        self.landButton.clicked.connect(self.set_land_mode)
        self.followButton.clicked.connect(self.set_follow_mode)
        self.emergencyButton.clicked.connect(self.set_kill_engine)

        self.batteryUpdatedSignal.connect(self._update_battery)

        #
        self._ui_update_timer = QTimer(self)
        self._ui_update_timer.timeout.connect(self._update_ui)

        # Start these ui elements invisible
        self.batteryBar.setTextVisible(False)

    # def got_message(self, address ,data):
    #     # address is given but not used
    #     # Send the data to where you want it from here
    #     print('callback', data)
    #     pass
    #
    # def ping(self):
    #     return True

    def _setup_states(self):
        parent_state = QState()

        # DISCONNECTED
        disconnected = QState(parent_state)
        disconnected.assignProperty(self, "status", "Disabled")
        disconnected.assignProperty(self.followButton, "text", "Follow Mode")
        disconnected.assignProperty(self.emergencyButton, "enabled", False)
        disconnected.assignProperty(self.liftButton, "enabled", False)
        disconnected.assignProperty(self.followButton, "enabled", False)
        disconnected.assignProperty(self.landButton, "enabled", False)
        self.batteryBar.setValue(3000)
        disconnected.entered.connect(self._flight_mode_disconnected_entered)

        # HOVERING
        hovering = QState(parent_state)
        hovering.assignProperty(self, "status", "Hovering...")
        hovering.assignProperty(self.followButton, "text", "Follow Mode")
        hovering.assignProperty(self.emergencyButton, "enabled", True)
        hovering.assignProperty(self.liftButton, "enabled", False)
        hovering.assignProperty(self.followButton, "enabled", True)
        hovering.assignProperty(self.landButton, "enabled", True)
        hovering.entered.connect(self._flight_mode_hovering_entered)

        # GROUNDED
        grounded = QState(parent_state)
        grounded.assignProperty(self, "status", "Grounded")
        grounded.assignProperty(self.followButton, "text", "Follow Mode")
        grounded.assignProperty(self.emergencyButton, "enabled", True)
        grounded.assignProperty(self.liftButton, "enabled", True)
        grounded.assignProperty(self.followButton, "enabled", False)
        grounded.assignProperty(self.landButton, "enabled", False)
        grounded.entered.connect(self._flight_mode_grounded_entered)

        # FOLLOW
        follow = QState(parent_state)
        follow.assignProperty(self, "status", "Follow Mode")
        follow.assignProperty(self.followButton, "text", "Stop")
        follow.assignProperty(self.emergencyButton, "enabled", True)
        follow.assignProperty(self.landButton, "enabled", True)
        follow.assignProperty(self.followButton, "enabled", False)
        follow.assignProperty(self.liftButton, "enabled", False)
        follow.entered.connect(self._flight_mode_follow_entered)

        # LIFT
        lift = QState(parent_state)
        lift.assignProperty(self, "status", "Lifting...")
        lift.assignProperty(self.emergencyButton, "enabled", True)
        lift.assignProperty(self.liftButton, "enabled", False)
        lift.assignProperty(self.followButton, "enabled", False)
        lift.assignProperty(self.landButton, "enabled", True)
        lift.entered.connect(self._flight_mode_lift_entered)

        # LAND
        land = QState(parent_state)
        land.assignProperty(self, "status", "Landing...")
        land.assignProperty(self.emergencyButton, "enabled", True)
        land.assignProperty(self.liftButton, "enabled", False)
        land.assignProperty(self.followButton, "enabled", False)
        land.assignProperty(self.landButton, "enabled", False)
        land.entered.connect(self._flight_mode_land_entered)

        def add_transition(mode, child_state, parent):
            transition = FlightModeTransition(mode)
            transition.setTargetState(child_state)
            parent.addTransition(transition)

        add_transition(FlightModeStates.LAND, land, parent_state)
        add_transition(FlightModeStates.LIFT, lift, parent_state)
        add_transition(FlightModeStates.HOVERING, hovering, parent_state)
        add_transition(FlightModeStates.FOLLOW, follow, parent_state)
        add_transition(FlightModeStates.GROUNDED, grounded, parent_state)
        add_transition(FlightModeStates.DISCONNECTED, disconnected,
                       parent_state)

        parent_state.setInitialState(disconnected)
        self._machine.addState(parent_state)
        self._machine.setInitialState(parent_state)
        self._machine.start()

    def _update_battery(self, timestamp, data, logconf):
        self.batteryBar.setValue(int(data["pm.vbat"] * 1000))

        color = UiUtils.COLOR_BLUE
        # TODO firmware reports fully-charged state as 'Battery',
        # rather than 'Charged'
        if data["pm.state"] in [BatteryStates.CHARGING, BatteryStates.CHARGED]:
            color = UiUtils.COLOR_GREEN
            self.charging = True
        elif data["pm.state"] == BatteryStates.LOW_POWER:
            color = UiUtils.COLOR_RED
            self.low_power = True
        elif data["pm.state"] == BatteryStates.BATTERY:
            self.low_power = False

        self.batteryBar.setStyleSheet(UiUtils.progressbar_stylesheet(color))
        self._aff_volts.setText(("%.3f" % data["pm.vbat"]))

    """
    update flight status is called when;
    - the CF is connected or disconnected
    - the QTM (or in our case the poseNet) is connected or disconnected
    it ensure that they are both connected before starting the flight controller.
    """

    def _update_flight_status(self):
        """
        assign old state to new state
        """
        prev_flying_enabled = self.flying_enabled
        """
        if there is a cf instance and a qtm connection instance
        (even if they are not connected)
        then flying is enabled
        """

        self.flying_enabled = (self._cf is not None
                               and self._cf_R is not None
                               and self._cf_L is not None)

        """
        if the flying enabled is not the same as prev_flying enabled"
        an additional check for security...?
        """
        if not prev_flying_enabled and self.flying_enabled:
            self.switch_flight_mode(FlightModeStates.GROUNDED)
            t1 = threading.Thread(target=self.flight_controller)
            t1.start()

        """
        if either the CF or QTM/Posenet Drops out.
        flight mode is disconnect
        """
        if prev_flying_enabled and not self.flying_enabled:
            self.switch_flight_mode(FlightModeStates.DISCONNECTED)

        else:
            pass

    """
    Although PyQt allows any Python callable to be used as a slot when
    connecting signals, it is sometimes necessary to explicitly mark a
    Python method as being a Qt slot and to provide a C++ signature for it.
    PyQt4 provides the pyqtSlot() function decorator to do this
    """

    @pyqtSlot(str)
    def _update_cf_status(self, status):
        self.cfStatusLabel.setText(status)

    @pyqtSlot(str)
    def _update_cf_status_L(self, status):
        self.cfStatusLabel_L.setText(status)

    @pyqtSlot(str)
    def _update_cf_status_R(self, status):
        self.cfStatusLabel_R.setText(status)

    @pyqtSlot(str)
    def _update_status(self, status):
        self.statusLabel.setText("{}".format(status))

    """
    A new Qt property may be defined using the pyqtProperty function.
    It is used in the same way as the standard Python property() function.
    In fact, Qt properties defined in this way also behave as Python properties.
    https://www.riverbankcomputing.com/static/Docs/PyQt5/qt_properties.html
    https://www.youtube.com/watch?v=jCzT9XFZ5bw
    """

    @pyqtProperty(str, notify=cfStatusChanged)
    def cfStatus(self):
        return

    @cfStatus.setter
    def cfStatus(self, value):
        if value != self._cf_status:
            self._cf_status = value
            self.cfStatusChanged.emit(value)

    @pyqtProperty(str, notify=cfStatusChanged_L)
    def cfStatus_L(self):
        return

    @cfStatus_L.setter
    def cfStatus_L(self, value):
        if value != self._cf_status_L:
            self._cf_status_L = value
            self.cfStatusChanged_L.emit(value)

    @pyqtProperty(str, notify=cfStatusChanged_R)
    def cfStatus_R(self):
        return

    @cfStatus_R.setter
    def cfStatus_R(self, value):
        if value != self._cf_status_R:
            self._cf_status_R = value
            self.cfStatusChanged_R.emit(value)

    @pyqtProperty(str, notify=statusChanged)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value != self._status:
            self._status = value
            self.statusChanged.emit(value)

    # '_cf' CALLBACK FUNCTIONS
    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""

        logger.debug("Crazyflie '_cf' connected to {}".format(link_uri))

        # Gui
        self.cfStatus = ': connected'

        self.reset_all_positions()

        self._helper_L.open_link(self.uri_L)
        self._helper_R.open_link(self.uri_R)

        self.t2 = threading.Thread(target=self.flight_logger, args=(self._helper.cf, 'cf_pos',link_uri))
        self.t2.start()

        # username is the URI for the drone
        self.link_uri_flying = link_uri
        self.set_phenotypes()
        self.load_accepted_positions()


        # log the battery state and voltage
        lg = LogConfig("Battery", 2000)
        lg.add_variable("pm.vbat", "float")
        lg.add_variable("pm.state", "int8_t")
        try:
            self._helper.cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self.batteryUpdatedSignal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))

        self._ui_update_timer.start(200)

        # TODO check the thread does not hang here.
        # self.server.send_message(message = {'username':link_uri})
        # print('sent', link_uri, type(link_uri))

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""

        logger.info("Crazyflie '_cf' disconnected from {}".format(link_uri))
        self.cfStatus = ': not connected'
        # self._helper_L.close_link()
        # self._helper_R.close_link()

        self._cf = None

        self._update_flight_status()

        self._ui_update_timer.stop()

    def _param_updated(self, name, value):
        """Callback when the registered parameter get's updated"""

        logger.debug("Updated '_cf' {0} to {1}".format(name, value))

    def _log_data_received(self, timestamp, data, log_conf):
        """Callback when the log layer receives new data"""
        logger.debug("Recieved from '_cf': {0}:{1}:{2}".format(timestamp, log_conf.name, data))

        if self._cf == None:
            self._cf = self._helper.cf

        if self._cf != None and self._cf_R != None and self._cf_L != None:
            self.cfStatus = (': logging')
            self.cfStatus_L = (': logging')
            self.cfStatus_R = (': logging')
            self._update_flight_status()

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""

        self.switch_flight_mode(FlightModeStates.DISCONNECTED)

        QMessageBox.about(self, "_cf Logging Error",
                          "_cf encountered an error when using log config"
                          " [{0}]: {1}".format(log_conf.name, msg))

    # '_cf_L' CALLBACK FUNCTIONS
    def _connected_L(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.debug("Crazyflie '_cf_L' connected to {}".format(link_uri))
        self.cfStatus_L = ': connected'

        self._helper_L.param.set_value('sound.effect', 12)
        self._helper_L.param.set_value('sound.freq', 0)

        self.t3 = threading.Thread(target=self.flight_logger, args=(self._helper_L, 'cf_pos_L',link_uri))
        self.t3.start()

    def _disconnected_L(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        logger.info("Crazyflie '_cf_L' disconnected from {}".format(link_uri))
        # Gui
        self.cfStatus_L = ': not connected'

        self._cf_L = None

    def _param_updated_L(self, name, value):
        """Callback when the registered parameter get's updated"""

        logger.debug("Updated '_cf_L' {0} to {1}".format(name, value))

    def _log_data_received_L(self, timestamp, data, log_conf):
        """Callback when the log layer receives new data"""

        logger.debug("Recieved from '_cf_L': {0}:{1}:{2}".format(timestamp, log_conf.name, data))

        if self._cf_L == None:
            self._cf_L = self._helper_L

        self.sound_controller(self._cf_L)

    def _logging_error_L(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""

        self.switch_flight_mode(FlightModeStates.DISCONNECTED)

        QMessageBox.about(self, "_cf_L Logging Error",
                          "_cf_L encountered an error when using log config"
                          " [{0}]: {1}".format(log_conf.name, msg))

    # '_cf_R' CALLBACK FUNCTIONS
    def _connected_R(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.debug("Crazyflie '_cf_R' connected to {}".format(link_uri))
        # Gui
        self.cfStatus_R = ': connected'

        self._helper_R.param.set_value('sound.effect', 12)
        self._helper_R.param.set_value('sound.freq', 0)

        self.t4 = threading.Thread(target=self.flight_logger, args=(self._helper_R, 'cf_pos_R',link_uri))
        self.t4.start()

    def _disconnected_R(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        logger.info("Crazyflie '_cf_R' disconnected from {}".format(link_uri))
        # Gui
        self.cfStatus_R = ': not connected'

        self._cf_R = None

    def _param_updated_R(self, name, value):
        """Callback when the registered parameter get's updated"""

        logger.debug("Updated '_cf_R' {0} to {1}".format(name, value))

    def _log_data_received_R(self, timestamp, data, log_conf):
        """Callback when the log layer receives new data"""

        logger.debug("Recieved from '_cf_R': {0}:{1}:{2}".format(timestamp, log_conf.name, data))

        if self._cf_R == None:
            self._cf_R = self._helper_R

        self.sound_controller(self._cf_R)

    def _logging_error_R(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""

        self.switch_flight_mode(FlightModeStates.DISCONNECTED)

        QMessageBox.about(self, "_cf_R Logging Error",
                          "_cf_R encountered an error when using log config"
                          " [{0}]: {1}".format(log_conf.name, msg))

    def _update_ui(self):
        # Update the data in the GUI
        self.cf_X.setText(("%0.4f" % self.cf_pos.x))
        self.cf_Y.setText(("%0.4f" % self.cf_pos.y))
        self.cf_Z.setText(("%0.4f" % self.cf_pos.z))

        self.cf_Roll.setText(("%0.2f" % self.cf_pos.roll))
        self.cf_Pitch.setText(("%0.2f" % self.cf_pos.pitch))
        self.cf_Yaw.setText(("%0.2f" % self.cf_pos.yaw))

        self.cf_L_X.setText(("%0.4f" % self.cf_pos_L.x))
        self.cf_L_Y.setText(("%0.4f" % self.cf_pos_L.y))
        self.cf_L_Z.setText(("%0.4f" % self.cf_pos_L.z))

        self.cf_L_Roll.setText(("%0.2f" % self.cf_pos_L.roll))
        self.cf_L_Pitch.setText(("%0.2f" % self.cf_pos_L.pitch))
        self.cf_L_Yaw.setText(("%0.2f" % self.cf_pos_L.yaw))

        self.cf_R_X.setText(("%0.4f" % self.cf_pos_R.x))
        self.cf_R_Y.setText(("%0.4f" % self.cf_pos_R.y))
        self.cf_R_Z.setText(("%0.4f" % self.cf_pos_R.z))

        self.cf_R_Roll.setText(("%0.2f" % self.cf_pos_R.roll))
        self.cf_R_Pitch.setText(("%0.2f" % self.cf_pos_R.pitch))
        self.cf_R_Yaw.setText(("%0.2f" % self.cf_pos_R.yaw))

    def set_phenotypes(self):
        # JULIAN AMBER
        if self.link_uri_flying[-10:] == 'A0A0A0A0A3':
            self.max_training_loops = 900
            self.leeway = .18
            self.spin_rate = .5
            self.starting_height = .9
        # MARGOT GREEN
        if self.link_uri_flying[-10:] == 'A0A0A0A0A4':
            self.max_training_loops = 800
            self.leeway = .16
            self.spin_rate = .4
            self.starting_height = .8
        # NINA BROWN
        if self.link_uri_flying[-10:] == 'A0A0A0A0A5':
            self.max_training_loops = 1200
            self.leeway = .24
            self.spin_rate = .8
            self.starting_height = 1.2
        # TIM FIST BLUE
        if self.link_uri_flying[-10:] == 'A0A0A0A0A6':
            self.max_training_loops = 1000
            self.leeway = .2
            self.spin_rate = .6
            self.starting_height = 1
        # TIM GOODSON AQUA
        if self.link_uri_flying[-10:] == 'A0A0A0A0A7':
            self.max_training_loops = 1100
            self.leeway = .22
            self.spin_rate = .7
            self.starting_height = 1.2

    def sound_controller(self,cf):
        if self.isTraining:
            self.current_freq += 1
        else:
            self.current_freq = self.starting_freq
        freq_list = [0, 0, 0, 0]
        # cf.param.set_value('sound.freq', 0)
        if self.freq_counter >= (len(freq_list) - 1):
            self.freq_counter = 0
        else:
            self.freq_counter += 1
        if self.link_uri_flying[-10:] == 'A0A0A0A0A3':
            freq_list = [10, 0, 7, 6]
            cf.param.set_value('sound.freq', freq_list[self.freq_counter] + self.current_freq)
        if self.link_uri_flying[-10:] == 'A0A0A0A0A4':
            freq_list = [10, 0, 6, 0]
            cf.param.set_value('sound.freq', freq_list[self.freq_counter] + self.current_freq)
        if self.link_uri_flying[-10:] == 'A0A0A0A0A5':
            freq_list = [6, 7, 10, 0]
            cf.param.set_value('sound.freq', freq_list[self.freq_counter] + self.current_freq)
        if self.link_uri_flying[-10:] == 'A0A0A0A0A6':
            freq_list = [6, 8, 11, 0]
            cf.param.set_value('sound.freq', freq_list[self.freq_counter] + self.current_freq)
        if self.link_uri_flying[-10:] == 'A0A0A0A0A7':
            freq_list = [12, 0, 6, 19]
            cf.param.set_value('sound.freq', freq_list[self.freq_counter] + self.current_freq)

        # time.sleep(.001)

    def load_accepted_positions(self):
    #     https://stackoverflow.com/questions/36965507/writing-a-dictionary-to-a-text-file
        filename = self.link_uri_flying[-10:] + '.json'
        try:
            with open(filename, 'r') as f:
                self.accepted_positions = json.loads(f.read())
                print('loaded %d position from save file' % (len(self.accepted_positions.keys())))
        except:
            with open(filename, 'w') as f:
                f.write(json.dumps(self.accepted_positions))

    def check_hand_position(self, lh_pos, cf_pos, rh_pos, save):
        if not self.isUnlocked:
            # print('764 self.isUnlocked = ', self.isUnlocked)
            if self.train_hand_position(lh_pos, cf_pos, rh_pos) is True:
                self.isTraining = True
                # print('training loop number', len(self.diff_dict['diff_Lx']))
                if len(self.diff_dict['diff_Lx']) > self.max_training_loops:
                    # print('769 self.isUnlocked = ', self.isUnlocked)
                    self.isUnlocked = True
                    self.isTraining = False
                    if save == 1:
                        self.save_accepted_position()
                    print('resetting')
                    self.diff_dict.clear()
            # ie if train_hand_position is False and you have more than 1 data point
            # ie ie dont clear the diff_dict unless you have more than x readings with high variance
            elif len(self.diff_dict['diff_Lx']) > 10:
                self.isTraining = False
                print('resetting')
                self.diff_dict.clear()

    def train_hand_position(self, lh_pos, cf_pos, rh_pos):
        # checks if the median of the toal hand positions are below a threshold.

        diff_Lx = cf_pos.x - lh_pos.x
        diff_Ly = cf_pos.y - lh_pos.y
        diff_Lz = cf_pos.z - lh_pos.z
        diff_Rx = cf_pos.x - rh_pos.x
        diff_Ry = cf_pos.y - rh_pos.y
        diff_Rz = cf_pos.z - rh_pos.z

        self.diff_dict['diff_Lx'].append(diff_Lx)
        self.diff_dict['diff_Ly'].append(diff_Ly)
        self.diff_dict['diff_Lz'].append(diff_Lz)
        self.diff_dict['diff_Rx'].append(diff_Rx)
        self.diff_dict['diff_Ry'].append(diff_Ry)
        self.diff_dict['diff_Rz'].append(diff_Rz)

        # if len(self.diff_dict['diff_Lx']) > 1:
        #     variance_list = [statistics.variance(self.diff_dict['diff_Lx']),
        #                      statistics.variance(self.diff_dict['diff_Ly']),
        #                      statistics.variance(self.diff_dict['diff_Lz']),
        #                      statistics.variance(self.diff_dict['diff_Rx']),
        #                      statistics.variance(self.diff_dict['diff_Ry']),
        #                      statistics.variance(self.diff_dict['diff_Rz'])]

        if len(self.diff_dict['diff_Lx']) > 1:
            min_max_list = [max((self.diff_dict['diff_Lx'])) - min((self.diff_dict['diff_Lx'])),
                           max((self.diff_dict['diff_Ly'])) - min((self.diff_dict['diff_Ly'])),
                           max((self.diff_dict['diff_Lz'])) - min((self.diff_dict['diff_Lz'])),
                           max((self.diff_dict['diff_Rx'])) - min((self.diff_dict['diff_Rx'])),
                           max((self.diff_dict['diff_Ry'])) - min((self.diff_dict['diff_Ry'])),
                           max((self.diff_dict['diff_Rz'])) - min((self.diff_dict['diff_Rz']))]

            false_list = [
                0 < x < self.max_training_variance
                # for x in variance_list
                for x in min_max_list
            ]
            # print('variance', statistics.mean(variance_list))
            # print('variance', statistics.mean(min_max_list))

            if all(false_list):
                # these are the relative xyz coordinates of the  left and right handpads relative to the drone
                self.diff_dict['diff_Lx_median'] = statistics.median(self.diff_dict['diff_Lx'])
                self.diff_dict['diff_Ly_median'] = statistics.median(self.diff_dict['diff_Ly'])
                self.diff_dict['diff_Lz_median'] = statistics.median(self.diff_dict['diff_Lz'])
                self.diff_dict['diff_Rx_median'] = statistics.median(self.diff_dict['diff_Rx'])
                self.diff_dict['diff_Ry_median'] = statistics.median(self.diff_dict['diff_Ry'])
                self.diff_dict['diff_Rz_median'] = statistics.median(self.diff_dict['diff_Rz'])
                return all(false_list)

        else:
            return False

    def save_accepted_position(self):
        now = datetime.now()
        position_name = now.strftime("%d-%m-%Y--%H:%M:%S")

        self.accepted_positions[position_name] = \
            [statistics.median(self.diff_dict['diff_Lx']), statistics.median(self.diff_dict['diff_Ly']),
             statistics.median(self.diff_dict['diff_Lz']),
             statistics.median(self.diff_dict['diff_Rx']), statistics.median(self.diff_dict['diff_Ry']),
             statistics.median(self.diff_dict['diff_Rz'])]

        filename = self.link_uri_flying[-10:] + '.json'

        with open(filename, 'w') as f:
            f.write(json.dumps(self.accepted_positions))
            print('file written')

    def check_condition(self, lh_pos, cf_pos, rh_pos, leeway):
        # print('check cond has staretd')

        accepted_position_diffs = {}

        for key, delta_list in self.accepted_positions.items():

            lh_diff = lh_pos.distance_to(
                Position(cf_pos.x - delta_list[0], cf_pos.y - delta_list[1], cf_pos.z - delta_list[2])
            )
            rh_diff = rh_pos.distance_to(
                Position(cf_pos.x - delta_list[3], cf_pos.y - delta_list[4], cf_pos.z - delta_list[5])
            )

            # Save values to dictionary if within leeway
            if lh_diff < leeway and rh_diff < leeway:
                accepted_position_diffs[key] = lh_diff + rh_diff

        # If any of our accepted positions are within the leeway, find the one with the minimum summed distance to
        # our current hand positions, and save the corresponding wand positions
        if len(accepted_position_diffs) > 0:

            best_accepted_position_key = min(accepted_position_diffs.items(), key=operator.itemgetter(1))[0]
            best_accepted_position = self.accepted_positions[best_accepted_position_key]

            self.end_of_wand_L.x = lh_pos.x + best_accepted_position[0]
            self.end_of_wand_L.y = lh_pos.y + best_accepted_position[1]
            self.end_of_wand_L.z = lh_pos.z + best_accepted_position[2]

            self.end_of_wand_R.x = rh_pos.x + best_accepted_position[3]
            self.end_of_wand_R.y = rh_pos.y + best_accepted_position[4]
            self.end_of_wand_R.z = rh_pos.z + best_accepted_position[5]

            return True

        return False

    def _flight_mode_land_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Trying to land at: x: {} y: {}'.format(
            self.current_goal_pos.x, self.current_goal_pos.y))
        self.initial_land_height = self.current_goal_pos.z
        print('flight_mode_land_entered')
        self._event.set()

    def _flight_mode_follow_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Entering follow mode')
        # TODO - RE INSTATE LAST WAND POS
        # self.last_valid_wand_pos = Position(0, 0, 1)
        print('flight_mode_follow_entered')
        self._event.set()

    def _flight_mode_lift_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Trying to lift at: {}'.format(
            self.current_goal_pos))
        print('flight_mode_lift_entered')
        self._event.set()

    def _flight_mode_hovering_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Hovering at: {}'.format(
            self.current_goal_pos))
        print('flight_mode_hovering_entered')
        self._event.set()

    def _flight_mode_grounded_entered(self):
        print('flight_mode_grounded_entered')
        self._event.set()

    def _flight_mode_disconnected_entered(self):
        self._cf_L.param.set_value('sound.freq', 0)
        self._cf_R.param.set_value('sound.freq', 0)
        self._cf_L.close_link()
        self._cf_R.close_link()
        print('flight_mode_disconnected_entered')
        self._event.set()

    def flight_logger(self, cf, key, link_uri):
        try:
            logger.info('Starting flight logger thread for {}'.format(key))

            received_signals = LogConfig(name='lighthouse', period_in_ms=1000)
            # below 50ms nans are called even though the cf can see the base station
            # probably because it is logging the variable before it is updated.
            received_signals.add_variable('lighthouse.bsReceive','uint16_t')

            log_position = LogConfig(name='Position', period_in_ms=50)
            log_position.add_variable('stateEstimate.x', 'float')
            log_position.add_variable('stateEstimate.y', 'float')
            log_position.add_variable('stateEstimate.z', 'float')
            log_position.add_variable('stateEstimate.roll', 'float')
            log_position.add_variable('stateEstimate.pitch', 'float')
            log_position.add_variable('stateEstimate.yaw', 'float')

            smoothing = 10

            roll_history = [0] * smoothing
            pitch_history = [0] * smoothing
            yaw_history = [0] * smoothing

            state_estimate = [0, 0, 0, 0, 0, 0]

            data_1 = {}
            data_2 = {}

            # PowerSwitch(link_uri).stm_power_cycle()
            time.sleep(1)

            self.reset_estimator(cf)

            time.sleep(0.1)

            if cf == self._helper.cf:
                received_signals.data_received_cb.add_callback(self._log_data_received)
                log_position.data_received_cb.add_callback(self._log_data_received)
                received_signals.error_cb.add_callback(self._log_error_signal)
                log_position.error_cb.add_callback(self._log_error_signal)
                print('_cf callbacks set')

            if cf == self._helper_L:
                received_signals.data_received_cb.add_callback(self._log_data_received_L)
                log_position.data_received_cb.add_callback(self._log_data_received_L)
                received_signals.error_cb.add_callback(self._log_error_signal_L)
                log_position.error_cb.add_callback(self._log_error_signal_L)
                print('_cf_L callbacks set')

            if cf == self._helper_R:
                received_signals.data_received_cb.add_callback(self._log_data_received_R)
                log_position.data_received_cb.add_callback(self._log_data_received_R)
                received_signals.error_cb.add_callback(self._log_error_signal_R)
                log_position.error_cb.add_callback(self._log_error_signal_R)
                print('_cf_R callbacks set')

            with SyncLogger(cf, [received_signals, log_position]) as log:
                for log_entry in log:
                    if 'lighthouse.bsReceive' in log_entry[1]:
                        data_1 = log_entry[1]

                        # if you cannot see ANY of the trackers.
                        if data_1['lighthouse.bsReceive'] == 0:
                            self.cf_pos_dict[key] = Position(float('nan'), float('nan'), float('nan'))
                            print(key, 'nan')

                    if 'stateEstimate.x' in log_entry[1]:
                        # if you can see ANY of the trackers.
                        if data_1.get('lighthouse.bsReceive') is not None:
                            if data_1.get('lighthouse.bsReceive') > 0:
                                data_2 = log_entry[1]
                                # print(data_2)
                                state_estimate[0] = data_2['stateEstimate.x']
                                state_estimate[1] = data_2['stateEstimate.y']
                                state_estimate[2] = data_2['stateEstimate.z']
                                # state_estimate[3] = data_2['stateEstimate.roll']
                                # state_estimate[4] = data_2['stateEstimate.pitch']
                                # state_estimate[5] = data_2['stateEstimate.yaw']

                                roll_history.append(data_2['stateEstimate.roll'])
                                roll_history.pop(0)
                                pitch_history.append(data_2['stateEstimate.pitch'])
                                pitch_history.pop(0)
                                yaw_history.append(data_2['stateEstimate.yaw'])
                                yaw_history.pop(0)

                                state_estimate[3] = statistics.mean(roll_history)
                                state_estimate[4] = statistics.mean(pitch_history)
                                state_estimate[5] = statistics.mean(yaw_history)

                                self.cf_pos_dict[key] = Position(state_estimate[0], state_estimate[1], state_estimate[2],
                                                                 state_estimate[3], state_estimate[4], state_estimate[5])
                    # if any of the cf's leave the logger loop
                    if not cf:
                        break
        finally:
            print('Terminating flight logger thread:', key)

    def flight_controller(self):
        try:
            logger.info('Starting flight controller thread')

            # The threshold for how many frames without tracking
            # is allowed before the cf's motors are stopped
            lost_tracking_threshold = 2500
            frames_without_tracking = 0
            position_hold_timer = 0
            spin_slow_down = self.spin_rate
            spin = 0
            self.length_from_wand = .25

            # The main flight control loop, the behaviour
            # is controlled by the state of "FlightMode"
            while self.flying_enabled:
                # unpacking updated dictionary data
                self.cf_pos = self.cf_pos_dict['cf_pos']
                self.cf_pos_L = self.cf_pos_dict['cf_pos_L']
                self.cf_pos_R = self.cf_pos_dict['cf_pos_R']

                # print('start of the main control loop')
                # Check that the position is valid and store it
                if self.cf_pos.is_valid():
                    self.valid_cf_pos = self.cf_pos
                    # print('valid cf pos is {}'.format(self.valid_cf_pos))
                    frames_without_tracking = 0

                    # check if drone is in centre of flight area before launch.
                    if self.flight_mode in [
                        FlightModeStates.GROUNDED,
                        ]:
                        message = None
                        # todo set back to 1
                        if self.valid_cf_pos.distance_to(Position(0, 0, 0)) > 100:
                            message = 'Drone not in centre of flying area'
                        if self.charging == True:
                            message = 'The connected drone is on the charger, turn off charging drone and try again'
                        if message is not None:
                            self.set_kill_engine(message)

                else:
                    # if it isn't, count number of frames
                    frames_without_tracking += 1

                    if frames_without_tracking > lost_tracking_threshold and \
                            self.flight_mode != FlightModeStates.GROUNDED:
                        self.set_kill_engine("Tracking lost")

                # If the cf is upside down, kill the motors
                if (self.valid_cf_pos.roll > 120 or self.valid_cf_pos.roll < -120) and \
                        self.flight_mode != FlightModeStates.GROUNDED:
                    self.set_kill_engine("Upside down")

                if self.low_power == True:
                    if self.flight_mode not in [
                        FlightModeStates.GROUNDED,
                        FlightModeStates.LAND
                    ]:
                        self.switch_flight_mode(FlightModeStates.LAND)
                        self.status = "Disabled - Low Power"

                # Switch on the FlightModeState and take actions accordingly
                # Wait so that any on state change actions are completed
                self._event.wait()

                if self.flight_mode == FlightModeStates.LAND:
                    self.isTraining = False
                    if self.cf_pos.is_valid():
                        spin += self.spin_rate
                        self.initial_land_height -= .001
                        self.send_setpoint(
                            Position(self.current_goal_pos.x,
                                     self.current_goal_pos.y, self.initial_land_height, yaw = spin))

                elif self.flight_mode == FlightModeStates.FOLLOW:
                    self.isTraining = False
                    self.isUnlocked = True
                    if self.cf_pos_L.is_valid() and self.cf_pos_R.is_valid():
                        self.valid_cf_pos_L = self.cf_pos_L
                        self.valid_cf_pos_R = self.cf_pos_R

                        spin = (self.valid_cf_pos_L.yaw + self.valid_cf_pos_R.yaw) / 2 + 180

                        self.mid_pos.x = (self.end_of_wand_L.x + self.end_of_wand_R.x) / 2
                        self.mid_pos.y = (self.end_of_wand_L.y + self.end_of_wand_R.y) / 2
                        self.mid_pos.z = (self.end_of_wand_L.z + self.end_of_wand_R.z) / 2

                        self.current_goal_pos = Position(self.mid_pos.x, self.mid_pos.y, self.mid_pos.z, yaw=spin)
                        self.status = "Follow Mode"
                        if self.check_condition(self.valid_cf_pos_L, self.valid_cf_pos, self.valid_cf_pos_R, self.leeway) is False:
                            self.switch_flight_mode(FlightModeStates.HOVERING)
                    else:
                        self.switch_flight_mode(FlightModeStates.HOVERING)

                    #the edge of the map
                    if (self.current_goal_pos.x < -1):
                        self.current_goal_pos.x = -1
                    if (self.current_goal_pos.x > 1):
                        self.current_goal_pos.x = 1
                    if (self.current_goal_pos.y < -1.4):
                        self.current_goal_pos.y = -1.4
                    if (self.current_goal_pos.y > 1.4):
                        self.current_goal_pos.y = 1.4
                    # if (self.current_goal_pos.z < -1.2):
                    #     self.current_goal_pos.z = -1.2
                    if (self.current_goal_pos.z > 2):
                        self.current_goal_pos.z = 2

                    self.send_setpoint(self.current_goal_pos)

                elif self.flight_mode == FlightModeStates.LIFT:
                    self.isTraining = False
                    if self.cf_pos.is_valid():
                        lift_height = self.floor_height + self.starting_height
                        spin += self.spin_rate
                        self.send_setpoint(
                            Position(self.current_goal_pos.x,
                                     self.current_goal_pos.y, (lift_height / self.lift_rate)))
                        self.lift_rate -= .01

                        if self.lift_rate < 1:
                            self.lift_rate = 1
                            # check if the crazyflie to reach each step of the goal
                            if self.valid_cf_pos.distance_to(
                                    Position(self.current_goal_pos.x,
                                             self.current_goal_pos.y, lift_height / self.lift_rate, yaw = spin)) < 0.17:
                                self.switch_flight_mode(FlightModeStates.HOVERING)

                elif self.flight_mode == FlightModeStates.HOVERING:
                    self.isTraining = False
                    self.isUnlocked = False
                    # assigned to local object as we will be reducing it when training is true
                    spin += self.spin_rate
                    if self.cf_pos_L.is_valid() and self.cf_pos_R.is_valid():
                        self.valid_cf_pos_L = self.cf_pos_L
                        self.valid_cf_pos_R = self.cf_pos_R
                        if self.valid_cf_pos_L.distance_to(self.valid_cf_pos) < 2 and \
                                self.valid_cf_pos_R.distance_to(self.valid_cf_pos) < 2:
                            # if save = 0 do not save.
                            save = 1
                            self.check_hand_position(self.valid_cf_pos_L, self.valid_cf_pos, self.valid_cf_pos_R, save)
                            if self.isTraining is True:
                                spin_slow_down -= (self.spin_rate/self.max_training_loops)
                                spin += spin_slow_down
                            else:
                                spin_slow_down = 0
                            # halved the leeway when in follow mode so that you don't accidentally snap into an already trained position
                            # that is different to what you are trying to trian.
                            if self.isUnlocked or self.check_condition(self.valid_cf_pos_L,self.valid_cf_pos,self.valid_cf_pos_R,(self.leeway*.75)):
                                spin_slow_down = 0
                                self.switch_flight_mode(FlightModeStates.FOLLOW)
                    self.send_setpoint(Position(self.current_goal_pos.x, self.current_goal_pos.y, self.current_goal_pos.z, yaw=spin))

                elif self.flight_mode == FlightModeStates.GROUNDED:
                    self.isTraining = False
                    self.isUnlocked = False
                    if self.cf_pos_L.is_valid() and self.cf_pos_R.is_valid():
                        self.valid_cf_pos_L = self.cf_pos_L
                        self.valid_cf_pos_R = self.cf_pos_R
                        if self.valid_cf_pos_L.distance_to(self.valid_cf_pos) < 1 and \
                                self.valid_cf_pos_R.distance_to(self.valid_cf_pos) < 1:
                            # if save = 0 do not save.
                            save = 0
                            self.check_hand_position(self.valid_cf_pos_L, self.valid_cf_pos, self.valid_cf_pos_R, save)
                        pass  # If gounded, the control is switched back to gamepad
                    # self._update_flight_status()
                time.sleep(0.001)

        except Exception as err:
            logger.error(err)
            self.cfStatus = str(err)

        logger.info('Terminating flight controller thread')

    """change the state of the state machine (?)"""

    def set_lift_mode(self):
        self.switch_flight_mode(FlightModeStates.LIFT)

    def set_land_mode(self):
        self.switch_flight_mode(FlightModeStates.LAND)

    def set_follow_mode(self):
        # Toggle follow mode on and off

        if self.flight_mode == FlightModeStates.FOLLOW:
            self.switch_flight_mode(FlightModeStates.HOVERING)
        else:
            self.switch_flight_mode(FlightModeStates.FOLLOW)

    def set_kill_engine(self, message):
        PowerSwitch(self.link_uri_flying).stm_power_cycle()
        self._helper.cf.close_link()
        # stm_power_cycle seems to stop the lighthouse deck from booting properly so we disconnect immediately afterwards.
        self.switch_flight_mode(FlightModeStates.DISCONNECTED)
        self.status = 'Disabled - ' + message

    def wait_for_position_estimator(self, cf):
        logger.info('Waiting for estimator to find stable position...')

        if cf == self._helper.cf:
            self.cfStatus = (
                'Waiting for estimator to find stable position... '
            )
        if cf == self._helper_L:
            self.cfStatus_L = (
                'Waiting for estimator to find stable position... '
            )
        if cf == self._helper_R:
            self.cfStatus_R = (
                'Waiting for estimator to find stable position... '
            )

        log_config = LogConfig(name='Kalman Variance', period_in_ms=100)
        log_config.add_variable('kalman.varPX', 'float')
        log_config.add_variable('kalman.varPY', 'float')
        log_config.add_variable('kalman.varPZ', 'float')

        var_y_history = [1000] * 10
        var_x_history = [1000] * 10
        var_z_history = [1000] * 10

        threshold = 0.001

        with SyncLogger(cf, log_config) as log:
            for log_entry in log:
                data = log_entry[1]

                var_x_history.append(data['kalman.varPX'])
                var_x_history.pop(0)
                var_y_history.append(data['kalman.varPY'])
                var_y_history.pop(0)
                var_z_history.append(data['kalman.varPZ'])
                var_z_history.pop(0)

                min_x = min(var_x_history)
                max_x = max(var_x_history)
                min_y = min(var_y_history)
                max_y = max(var_y_history)
                min_z = min(var_z_history)
                max_z = max(var_z_history)

                # print("{} {} {}".
                # format(max_x - min_x, max_y - min_y, max_z - min_z))

                if (max_x - min_x) < threshold and (
                        max_y - min_y) < threshold and (
                        max_z - min_z) < threshold:
                    logger.info("Position found with error in, x: {}, y: {}, "
                                "z: {}".format(max_x - min_x,
                                               max_y - min_y,
                                               max_z - min_z))
                    if (max_x - min_x) == 0 and (
                            max_y - min_y) == 0 and (
                            max_z - min_z) == 0:
                        # place drone on a flat surface and wait for sabilization before connecting
                        if cf == self._helper.cf:
                            self.cfStatus = (
                                ': drone did not stabilize before radio connection'
                            )
                        if cf == self._helper_L:
                            self.cfStatus_L = (
                                ': drone did not stabilize before radio connection'
                            )
                        if cf == self._helper_R:
                            self.cfStatus_R = (
                                ': drone did not stabilize before radio connection'
                            )
                    else:
                        if cf == self._helper.cf:
                            self.cfStatus = (
                                ': stabilised'
                            )
                        if cf == self._helper_L:
                            self.cfStatus_L = (
                                ': stabilised'
                            )
                        if cf == self._helper_R:
                            self.cfStatus_R = (
                                ': stabilised'
                            )

                        break

    def reset_estimator(self, cf):
        # Reset the kalman filter

        cf.param.set_value('kalman.resetEstimation', '1')
        time.sleep(0.1)
        cf.param.set_value('kalman.resetEstimation', '0')

        self.wait_for_position_estimator(cf)

    def switch_flight_mode(self, mode):
        # Handles the behaviour of switching between flight modes
        self.flight_mode = mode

        # Handle client input control.
        # Disable gamepad input if we are not grounded
        if self.flight_mode in [
            FlightModeStates.GROUNDED,
            FlightModeStates.DISCONNECTED,
        ]:
            self._helper.mainUI.disable_input(False)
        else:
            self._helper.mainUI.disable_input(True)

        self._event.clear()
        # # Threadsafe call
        self._machine.postEvent(FlightModeEvent(mode))

        logger.info('Switching Flight Mode to: %s', mode)

        # # send a message over the socket to start and stop logging
        # if str(mode) == "FlightModeStates.FOLLOW":
        #     self.server.send_message(message={"flightmode" : 'follow'})
        # else:
        #     self.server.send_message(message={"flightmode" : 'not follow'})
        #     print('sending flight mode over socket', mode)

    def send_setpoint(self, pos):
        # Wraps the send command to the crazyflie
        if self._cf is not None:
            if pos.z <= self.floor_height:
                self._cf.commander.send_stop_setpoint()
                self.switch_flight_mode(FlightModeStates.GROUNDED)
            else:
                self._cf.commander.send_position_setpoint(pos.x, pos.y, pos.z, pos.yaw)


    def reset_all_positions(self):
        # The position and rotation of the cf and wand obtained by the
        # lighthouse tracking, if it cant be tracked the position becomes Nan
        # cf_pos_dict is what is updated by the three async flight logger calls.
        # they need to be unpacked at the top of the flight controller loop
        self.cf_pos_dict = {'cf_pos': Position(0, 0, 0),
                            'cf_pos_L': Position(0, 0, 0),
                            'cf_pos_R': Position(0, 0, 0)}
        self.cf_pos = Position(0, 0, 0)
        self.cf_pos_L = Position(0, 0, 0)
        self.cf_pos_R = Position(0, 0, 0)

        # The regular cf_pos can a times due to lost tracing become Nan,
        # this the latest known valid cf position
        self.valid_cf_pos = Position(0, 0, 0)
        self.valid_cf_pos_L = Position(0, 0, 0)
        self.valid_cf_pos_R = Position(0, 0, 0)

        self.end_of_wand_L = Position(0, 0, 0)
        self.end_of_wand_R = Position(0, 0, 0)

        self.mid_pos = Position(0, 0, 0)
        print("Positions Reset")

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
        # if any of them were nan then the function returs false
        # print('is valid has run')
        return self.x == self.x and self.y == self.y and self.z == self.z

    def __str__(self):
        return "x: {} y: {} z: {} Roll: {} Pitch: {} Yaw: {}".format(
            self.x, self.y, self.z, self.roll, self.pitch, self.yaw)


