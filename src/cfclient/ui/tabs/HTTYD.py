#!/usr/bin/env python
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

"""
An example template for a tab in the Crazyflie Client. It comes pre-configured
with the necessary QT Signals to wrap Crazyflie API callbacks and also
connects the connected/disconnected callbacks.
"""

import logging
from enum import Enum

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, pyqtProperty
from PyQt5.QtCore import QStateMachine, QState, QEvent, QTimer
from PyQt5.QtCore import QAbstractTransition
from PyQt5.QtWidgets import QMessageBox

import cfclient
from cfclient.ui.tab import Tab

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
    CIRCLE = 7
    RECORD = 8

class HTTYD(Tab, HTTYD_tab_class):
    """Tab for plotting logging data"""

    """Define some signals that will emit some string,
    signals a are usually sent by buttons
    these signals need to be connected to a slot/slots. 
    so for example, when the CF is connected, a bunch of things
    in the GUI happen. 
    
    https://youtu.be/GIg9ehmGJHY?t=1420
    """
    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_data_signal = pyqtSignal(int, object, object)
    _log_error_signal = pyqtSignal(object, str)
    _param_updated_signal = pyqtSignal(str, str)

    cfStatusChanged = pyqtSignal(str)
    statusChanged = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(HTTYD, self).__init__(*args)
        self.setupUi(self)

        self._machine = QStateMachine()
        self._setup_states()

        self.tabName = "HTTYD"
        self.menuName = "HTTYD Tab"
        self.tabWidget = tabWidget

        self._setup_states()

        self._helper = helper

        # assign the label to the _cf_status_ string
        self._cf_status = self.cfStatusLabel.text()
        self._status = self.statusLabel.text()

        # initial flight mode
        self.flying_enabled = False
        self.switch_flight_mode(FlightModeStates.DISCONNECTED)

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._log_data_signal.connect(self._log_data_received)
        self._param_updated_signal.connect(self._param_updated)

        # connect the status change signal to the update status
        # funciton
        self.statusChanged.connect(self._update_status)
        self.cfStatusChanged.connect(self._update_cf_status)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        # Connect the UI elements
        self.liftButton.clicked.connect(self.set_lift_mode)
        self.landButton.clicked.connect(self.set_land_mode)
        self.followButton.clicked.connect(self.set_follow_mode)
        self.emergencyButton.clicked.connect(self.set_kill_engine)

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
        grounded.assignProperty(self, "status", "Landed")
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
        follow.assignProperty(self.recordButton, "enabled", False)
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
        add_transition(FlightModeStates.GROUNDED, grounded, parent_state)
        add_transition(FlightModeStates.DISCONNECTED, disconnected,
                       parent_state)

        parent_state.setInitialState(disconnected)
        self._machine.addState(parent_state)
        self._machine.setInitialState(parent_state)
        self._machine.start()

    def _update_flight_status(self):
        prev_flying_enabled = self.flying_enabled
        self.flying_enabled = self._cf is not None
                              # and \
            # self._qtm_connection is not None

        if not prev_flying_enabled and self.flying_enabled:
            self.switch_flight_mode(FlightModeStates.GROUNDED)
            # t = threading.Thread(target=self.flight_controller)
            # t.start()

        if prev_flying_enabled and not self.flying_enabled:
            self.switch_flight_mode(FlightModeStates.DISCONNECTED)

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
    def _update_status(self, status):
        self.statusLabel.setText("Status: {}".format(status))


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

    @pyqtProperty(str, notify=statusChanged)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value != self._status:
            self._status = value
            self.statusChanged.emit(value)

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""

        self._cf = self._helper.cf
        self._update_flight_status()

        logger.debug("Crazyflie connected to {}".format(link_uri))

        # Gui
        self.cfStatus = ': connected'

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""

        logger.info("Crazyflie disconnected from {}".format(link_uri))
        self.cfStatus = ': not connected'
        self._cf = None
        self._update_flight_status()

    def _param_updated(self, name, value):
        """Callback when the registered parameter get's updated"""

        logger.debug("Updated {0} to {1}".format(name, value))

    def _log_data_received(self, timestamp, data, log_conf):
        """Callback when the log layer receives new data"""

        logger.debug("{0}:{1}:{2}".format(timestamp, log_conf.name, data))

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""

        QMessageBox.about(self, "Example error",
                          "Error when using log config"
                          " [{0}]: {1}".format(log_conf.name, msg))

    def _flight_mode_disconnected_entered(self):
        # self._event.set()
        print('flight_mode_disconnected_entered')
        pass

    def _flight_mode_hovering_entered(self):
        # self.current_goal_pos = self.valid_cf_pos
        # logger.info('Hovering at: {}'.format(
        #     self.current_goal_pos))
        # self._event.set()
        print('flight_mode_hovering_entered')
        pass

    def _flight_mode_grounded_entered(self):
        # self._event.set()
        print('flight_mode_grounded_entered')
        pass

    def _flight_mode_follow_entered(self):
        # self.last_valid_wand_pos = Position(0, 0, 1)
        # self._event.set()
        pass

    def _flight_mode_lift_entered(self):
        # self.current_goal_pos = self.valid_cf_pos
        # logger.info('Trying to lift at: {}'.format(
        #     self.current_goal_pos))
        # self._event.set()
        print('flight_mode_lift_entered')
        pass

    def _flight_mode_land_entered(self):
        # self.current_goal_pos = self.valid_cf_pos
        # logger.info('Trying to land at: x: {} y: {}'.format(
        #     self.current_goal_pos.x, self.current_goal_pos.y))
        # self.land_rate = 1
        # self._event.set()
        print('flight_mode_land_entered')
        pass

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

    def set_kill_engine(self):
        # self.send_setpoint(Position(0, 0, 0))
        self.switch_flight_mode(FlightModeStates.GROUNDED)
        logger.info('Stop button pressed, kill engines')

    def switch_flight_mode(self, mode):
        # Handles the behaviour of switching between flight modes
        self.flight_mode = mode

        # Handle client input control.
        # Disable gamepad input if we are not grounded
        if self.flight_mode in [
            FlightModeStates.GROUNDED,
            FlightModeStates.DISCONNECTED,
            FlightModeStates.RECORD
        ]:
            self._helper.mainUI.disable_input(False)
        else:
            self._helper.mainUI.disable_input(True)

        # self._event.clear()
        # # Threadsafe call
        self._machine.postEvent(FlightModeEvent(mode))

        logger.info('Switching Flight Mode to: %s', mode)



