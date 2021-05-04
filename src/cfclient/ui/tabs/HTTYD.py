
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
import math
import time
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

        self.server = SocketManager(self, server = True, port=5050)

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
        self.server.listen()

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

        # initial flight mode
        self.flying_enabled = False
        self.switch_flight_mode(FlightModeStates.DISCONNECTED)
        self.path_pos_threshold = 0.2

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

    def got_message(self, address ,data):
        # address is given but not used
        # Send the data to where you want it from here
        print('callback', data)
        pass

    def ping(self):
        return True

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
        self.statusLabel.setText("System Status: {}".format(status))

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

        self.link_uri_flying = link_uri
        # username is the URI for the drone

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
        self.server.send_message(message = {'username':link_uri})
        print('sent', link_uri, type(link_uri))

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""

        logger.info("Crazyflie '_cf' disconnected from {}".format(link_uri))
        self.cfStatus = ': not connected'

        self._helper_L.close_link()
        self._helper_R.close_link()

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

    def _flight_mode_land_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Trying to land at: x: {} y: {}'.format(
            self.current_goal_pos.x, self.current_goal_pos.y))
        self.land_rate = 1
        print('flight_mode_land_entered')
        self._event.set()

    def _flight_mode_follow_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Entering follow mode')
        # TODO - RE INSTATE LAST WAND POS
        # self.last_valid_wand_pos = Position(0, 0, 1)
        self._event.set()

    def _flight_mode_lift_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Trying to lift at: {}'.format(
            self.current_goal_pos))
        # divides the goal pos (x) by n eg x/n, x/n-1, x/n-2... x/1
        self.lift_rate = 3
        self._event.set()

    def _flight_mode_hovering_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Hovering at: {}'.format(
            self.current_goal_pos))
        self._event.set()

    def _flight_mode_grounded_entered(self):
        self._event.set()
        print('flight_mode_grounded_entered')

    def _flight_mode_disconnected_entered(self):
        self._event.set()
        print('flight_mode_disconnected_entered')

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
                                state_estimate[3] = data_2['stateEstimate.roll']
                                state_estimate[4] = data_2['stateEstimate.pitch']
                                state_estimate[5] = data_2['stateEstimate.yaw']
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
            spin = 0
            # this adds a little room for the x y and z values.
            leeway_min = .2
            leeway_max = .4
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
                        if self.valid_cf_pos.distance_to(Position(0, 0, 0)) > 1:
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
                    if self.cf_pos.is_valid():
                        spin += 0
                        self.send_setpoint(
                            Position(
                                self.current_goal_pos.x,
                                self.current_goal_pos.y,
                                (self.current_goal_pos.z / self.land_rate),
                                yaw=spin))
                        # Check if the cf has reached the  position,
                        # if it has set a new position

                        if self.valid_cf_pos.distance_to(
                                Position(self.current_goal_pos.x,
                                         self.current_goal_pos.y,
                                         self.current_goal_pos.z / self.land_rate
                                         )) < self.path_pos_threshold:
                            self.land_rate *= 1.1

                        if self.land_rate > 1000:
                            self.send_setpoint(Position(self.current_goal_pos.x, self.current_goal_pos.y, 0.001))
                            self.switch_flight_mode(FlightModeStates.GROUNDED)

                elif self.flight_mode == FlightModeStates.FOLLOW:
                    if self.cf_pos_L.is_valid() and self.cf_pos_R.is_valid():
                        self.valid_cf_pos_L = self.cf_pos_L
                        self.valid_cf_pos_R = self.cf_pos_R

                        # # Simple midpoint.
                        self.mid_pos.x = (self.valid_cf_pos_L.x + self.valid_cf_pos_R.x) / 2
                        self.mid_pos.y = (self.valid_cf_pos_L.y + self.valid_cf_pos_R.y) / 2
                        self.mid_pos.z = -.25 + (self.valid_cf_pos_L.z + self.valid_cf_pos_R.z) / 2

                        # """find the mid point between two points a certain distance away from the wands"""
                        # self.end_of_wand_L.x = self.valid_cf_pos_L.x + round(
                        #     math.cos(math.radians(self.valid_cf_pos_L.pitch)), 4) * self.length_from_wand
                        # self.end_of_wand_L.y = self.valid_cf_pos_L.y + round(
                        #     math.cos(math.radians(self.valid_cf_pos_L.roll)), 4) * self.length_from_wand
                        # self.end_of_wand_L.z = self.valid_cf_pos_L.z + round(
                        #     math.sin(math.radians(self.valid_cf_pos_L.pitch)), 4) * self.length_from_wand

                        # self.end_of_wand_R.x = self.valid_cf_pos_R.x + round(
                        #     math.cos(math.radians(self.valid_cf_pos_R.pitch)), 4) * self.length_from_wand
                        # self.end_of_wand_R.y = self.valid_cf_pos_R.y + round(
                        #     math.cos(math.radians(self.valid_cf_pos_R.roll)), 4) * self.length_from_wand
                        # self.end_of_wand_R.z = self.valid_cf_pos_R.z + round(
                        #     math.sin(math.radians(self.valid_cf_pos_R.pitch)), 4) * self.length_from_wand

                        # self.mid_pos.x = self.end_of_wand_L.x + (.5) * (self.end_of_wand_R.x - self.end_of_wand_L.x)
                        # self.mid_pos.y = self.end_of_wand_L.y + (.5) * (self.end_of_wand_R.y - self.end_of_wand_L.y)
                        # self.mid_pos.z = self.end_of_wand_L.z + (.5) * (self.end_of_wand_R.z - self.end_of_wand_L.z)

                        """if the next move is not too far away from the drone (ie too fast)"""
                        if self.valid_cf_pos.distance_to(self.mid_pos) < leeway_min:
                            self.current_goal_pos = self.mid_pos


                        elif self.valid_cf_pos.distance_to(self.mid_pos) > leeway_max:
                            self.current_goal_pos = self.valid_cf_pos
                            print('drone too fast')

                    else:
                        self.current_goal_pos = self.valid_cf_pos
                        print('wands not valid')


                    # if (self.current_goal_pos.x < -1):
                    #     self.current_goal_pos.x = -1
                    # if (self.current_goal_pos.x > 1):
                    #     self.current_goal_pos.x = 1
                    # if (self.current_goal_pos.y < -1):
                    #     self.current_goal_pos.y = -1
                    # if (self.current_goal_pos.y > 1):
                    #     self.current_goal_pos.y = 1
                    # if (self.current_goal_pos.z < 0):
                    #     self.current_goal_pos.z = 0
                    # if (self.current_goal_pos.z > 1.6):
                    #     self.current_goal_pos.z = 1.6
                    # if (self.current_goal_pos.z < .8):
                    #     self.current_goal_pos.z = .8

                    self.send_setpoint(self.current_goal_pos)


                elif self.flight_mode == FlightModeStates.LIFT:
                    lift_height = .5

                    self.send_setpoint(
                        Position(self.current_goal_pos.x,
                                 self.current_goal_pos.y, (lift_height / self.lift_rate)))
                    self.lift_rate -= .01
                    # print(self.lift_rate)

                    if self.lift_rate < 1:
                        self.lift_rate = 1
                        # check if the crazyflie to reach each step of the goal
                        if self.valid_cf_pos.distance_to(
                                Position(self.current_goal_pos.x,
                                         self.current_goal_pos.y, lift_height / self.lift_rate)) < 0.17:
                            self.switch_flight_mode(FlightModeStates.HOVERING)

                elif self.flight_mode == FlightModeStates.HOVERING:
                    self.send_setpoint(self.current_goal_pos)
                    # print('goal pos =', self.current_goal_pos.z)

                elif self.flight_mode == FlightModeStates.GROUNDED:
                    # if self.cf_pos_L.is_valid():
                    #     self.valid_cf_pos_L = self.cf_pos_L
                    #
                    # if self.cf_pos_R.is_valid():
                    #     self.valid_cf_pos_R = self.cf_pos_R
                    #
                    # if self.cf_pos_L.is_valid() and self.cf_pos_R.is_valid():
                    #     """find the mid point between two points a certain distance away from the wands"""
                    #     self.end_of_wand_L.x = self.valid_cf_pos_L.x + round(
                    #         math.cos(math.radians(self.valid_cf_pos_L.pitch)), 4) * self.length_from_wand
                    #     self.end_of_wand_L.y = self.valid_cf_pos_L.y + round(
                    #         math.cos(math.radians(self.valid_cf_pos_L.roll)), 4) * self.length_from_wand
                    #     self.end_of_wand_L.z = self.valid_cf_pos_L.z + round(
                    #         math.sin(math.radians(self.valid_cf_pos_L.pitch)), 4) * self.length_from_wand
                    #
                    #     self.end_of_wand_R.x = self.valid_cf_pos_R.x + round(
                    #         math.cos(math.radians(self.valid_cf_pos_R.pitch)), 4) * self.length_from_wand
                    #     self.end_of_wand_R.y = self.valid_cf_pos_R.y + round(
                    #         math.cos(math.radians(self.valid_cf_pos_R.roll)), 4) * self.length_from_wand
                    #     self.end_of_wand_R.z = self.valid_cf_pos_R.z + round(
                    #         math.sin(math.radians(self.valid_cf_pos_R.pitch)), 4) * self.length_from_wand
                    #
                    # print(self.end_of_wand_L.z)


                    pass  # If gounded, the control is switched back to gamepad

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

        # send a message over the socket to start and stop logging
        if str(mode) == "FlightModeStates.FOLLOW":
            self.server.send_message(message={"flightmode" : 'follow'})
        else:
            self.server.send_message(message={"flightmode" : 'not follow'})
            print('sending flight mode over socket', mode)

    def send_setpoint(self, pos):
        # Wraps the send command to the crazyflie
        if self._cf is not None:
            if pos.z <= 0:
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


