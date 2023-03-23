from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtWidgets import QDialog
from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QMessageBox, QVBoxLayout, QCheckBox, QButtonGroup
from PyQt6.QtWidgets import QStyleFactory
import PyQt6.QtCore as pyqt6
from PyQt6 import uic
from helper import res_path, classlistToIds
from PyQt6.QtCore import QTimer
import main
import struct
from base_ui import WidgetUI
from base_ui import CommunicationHandler
import portconf_ui


class RmdUI(WidgetUI, CommunicationHandler):
    RMD_STATES = ["IDLE", "WAIT_READY", "START_RUNNING", "RUNNING"]
    RMD_ERRORS = {"none": 0x0000, "motor_stall": 0x0002, "low_pressure": 0x0004, "overvoltage": 0x0008, "overcurrent": 0x0010,
                  "power_overrun": 0x0040, "speeding": 0x0100, "motor_over_temperature": 0x1000, "encoder_calibration_error": 0x2000}

    def __init__(self, main=None, unique=None):
        WidgetUI.__init__(self, main, 'rmd.ui')
        CommunicationHandler.__init__(self)
        self.main = main  # type: main.MainUi

        self.isRunning = False

        self.timer = QTimer(self)
        self.canOptions = portconf_ui.CanOptionsDialog(0, "CAN", main)
        self.canSettings_apply.clicked.connect(self.applyCanSettings)
        self.maxTorque_apply.clicked.connect(self.applyMaxTorque)
        self.pushButton_cansettings.clicked.connect(self.canOptions.exec)
        self.homeButton.clicked.connect(self.home)
        self.planAccelpushButton.clicked.connect(self.writePlanAccel)
        self.setOffsetButton.clicked.connect(self.setOffset)
        self.setRmdCanIdButton.clicked.connect(self.setRmdCanId)
        self.setRmdBaudrateButton.clicked.connect(self.setRmdBaudrate)
        self.resetMultiturnButton.clicked.connect(self.resetMultiturnValue)
        self.stopButton.clicked.connect(self.toggleRunning)
        # self.pushButton_anticogging.clicked.connect(self.antigoggingBtn) #TODO test first
        self.timer.timeout.connect(self.updateTimer)
        self.prefix = unique
        self.connected = False

        self.textEdit.setMarkdown(self.textEdit.toMarkdown())
        style = QStyleFactory.create('Windows')
        self.singleturn_dial.setStyle(style)

        self.kp_slider.valueChanged.connect(self.kp_val.setValue)
        self.ki_slider.valueChanged.connect(self.ki_val.setValue)
        self.vp_slider.valueChanged.connect(self.vp_val.setValue)
        self.vi_slider.valueChanged.connect(self.vi_val.setValue)
        self.ip_slider.valueChanged.connect(self.ip_val.setValue)
        self.ii_slider.valueChanged.connect(self.ii_val.setValue)

        self.kp_val.valueChanged.connect(self.kp_slider.setValue)
        self.ki_val.valueChanged.connect(self.ki_slider.setValue)
        self.vp_val.valueChanged.connect(self.vp_slider.setValue)
        self.vi_val.valueChanged.connect(self.vi_slider.setValue)
        self.ip_val.valueChanged.connect(self.ip_slider.setValue)
        self.ii_val.valueChanged.connect(self.ii_slider.setValue)

        self.advancedButton.clicked.connect( self.toggleAdvanced )

        self.readPidButton.clicked.connect( self.readPid )
        self.submitPidButton.clicked.connect( self.submitPid )

        self.pos = 0.0
        self.posOffset = 0.0

        self.register_callback("rmd", "canid", self.spinBox_id.setValue, self.prefix, int)
        self.register_callback("rmd", "connected", self.connectedCb, self.prefix, int)
        self.register_callback("rmd", "maxtorque", self.updateTorque, self.prefix, int)
        self.register_callback("rmd", "errors", lambda v: self.showErrors(v), self.prefix, int)
        self.register_callback("rmd", "state", lambda v: self.stateCb(v), self.prefix, int)
        self.register_callback("rmd", "voltage", self.voltageCb, self.prefix, int)
        self.register_callback("rmd", "apos", self.angPosCb, self.prefix, int)
        self.register_callback("rmd", "pos_turns", self.posTurnsCb, self.prefix, int)
        self.register_callback("rmd", "pos_turns_offset", self.posTurnsOffsetCb, self.prefix, int)
        self.register_callback("rmd", "single_pos", self.singlePosCb, self.prefix, int)
        self.register_callback("rmd", "single_offset", self.singleOffsetCb, self.prefix, int)
        self.register_callback("rmd", "multi_pos", self.multiPosCb, self.prefix, int)
        self.register_callback("rmd", "multi_pos_raw", self.multiPosRawCb, self.prefix, int)
        self.register_callback("rmd", "multi_offset", self.multiOffsetCb, self.prefix, int)
        self.register_callback("rmd", "single_ang", self.singleAngCb, self.prefix, int)
        self.register_callback("rmd", "multi_ang", self.multiAngCb, self.prefix, int)
        self.register_callback("rmd", "torque", self.torqueCb, self.prefix, int)
        self.register_callback("rmd", "pid", self.pidCb, self.prefix, int)

        self.init_ui()

    # Tab is currently shown
    def showEvent(self, event):
        self.init_ui()
        self.timer.start(25)

    # Tab is hidden
    def hideEvent(self, event):
        self.timer.stop()

    def init_ui(self):
        self.angPosSlider.setRange(-3000, 3000)
        self.curTorqueSlider.setRange(-75, 75)
        self.debugBox.setHidden(not self.advancedButton.isChecked())
        self.motionBox.setHidden(not self.advancedButton.isChecked())

        commands = ["canid", "canspd", "maxtorque"]
        self.send_commands("rmd", commands, self.prefix)

    def toggleAdvanced(self, checked):
        self.advancedButton.setArrowType( pyqt6.Qt.ArrowType.DownArrow if checked else pyqt6.Qt.ArrowType.RightArrow)
        self.debugBox.setHidden(not checked)
        self.motionBox.setHidden(not checked)

    def toggleRunning(self):
        self.isRunning = not self.isRunning
        if(self.isRunning):
            self.stopButton.setText("STOP")
            self.send_value("rmd", "start", 0, instance=self.prefix)
        else:
            self.stopButton.setText("RUN")
            self.send_value("rmd", "stop", 0, instance=self.prefix)

    def connectedCb(self, v):
        self.connected = False if v == 0 else True

    # def updateCanSpd(self,preset):
    #     self.comboBox_baud.setCurrentIndex(preset-3) # 3 is lowest preset!

    def updateTorque(self, torque):
        self.maxTorqueSpinBox.setValue(torque/100)

    def voltageCb(self, v):
        if not self.connected:
            self.label_voltage.setText("Not connected")
            return
        self.label_voltage.setText("{}V".format(v/10))

    def posTurnsCb(self, v):
        self.pos = float(v)/10000
        self.turns_val.setText("{:.3f}".format(self.pos))
        self.turnsAndOffset_val.setText("{:.3f}".format(self.pos - self.posOffset))

    def posTurnsOffsetCb(self, v):
        self.posOffset = float(v)/10000
        self.turnsOffset_val.setText("{:.3f}".format(v/10000))

    def angPosCb(self, v):
        pass

    def singleAngCb(self, v):
        self.angPosLabel.setText("{:.6f}".format(v/100))
        self.angPosSlider.setValue(v)

    def multiAngCb(self, v):
        self.angPosLabel.setText("{:.6f}".format(v/100))
        self.angPosSlider.setValue(v)

    def singlePosCb(self, v):
        self.singleturn_dial.setValue(v)
        self.singlePosRaw_val.setText("{}".format(v))

    def singleOffsetCb(self, v):
        self.singleOffset_val.setText("{}".format(v))
    
    def multiPosCb(self, v):
        self.multiPos_val.setText("{}".format(v))

    def multiPosRawCb(self, v):
        self.multiPosRaw_val.setText("{}".format(v))

    def multiOffsetCb(self, v):
        self.multiOffset_val.setText("{}".format(v))

    def torqueCb(self, v):
        torqueConstant = 2.6  # N.m/A
        self.curTorqueLabel.setText("{:.2f}".format(v/100*torqueConstant))
        self.curTorqueSlider.setValue(v)

    def showErrors(self, codes):
        if not self.connected:
            self.label_errornames.setText("Not connected")
            return
        errs = []
        if (codes == 0):
            errs = ["None"]

        for name, i in (self.RMD_ERRORS.items()):
            if (codes & i != 0):
                errs.append(name)
        if len(errs) == 0:
            errs = [str(codes)]
        errString = "\n".join(errs)

        self.label_errornames.setText(errString)

    def stateCb(self, dat):
        if not self.connected:
            self.label_state.setText("Not connected")
            return
        if (dat < len(self.RMD_STATES)):
            self.label_state.setText(self.RMD_STATES[dat])
        else:
            self.label_state.setText(str(dat))

    def updateTimer(self):
        pass
        self.send_commands("rmd", ["connected", "voltage", "error", "state", "pos_turns", "pos_turns_offset", "torque", "multi_pos_raw", "multi_offset", "single_pos", "single_offset", "multi_ang"], self.prefix)

    def writePlanAccel(self):
        pass

    def readPid(self):
        self.send_command("rmd", "pid", self.prefix)

    def submitPid(self):
        pass

    def pidCb(self, v):
        # Unpack the PID parameters from the uint64
        ip, ii, vp, vi, kp, ki, _, _ = struct.unpack('8B', v.to_bytes(8, 'little'))
        self.kp_val.setValue(kp)
        self.ki_val.setValue(ki)
        self.vp_val.setValue(vp)
        self.vi_val.setValue(vi)
        self.ip_val.setValue(ip)
        self.ii_val.setValue(ii)
        pass

    def setOffset(self):
        self.send_value("rmd", "multi_offset", 0, instance=self.prefix)

    def home(self):
        pass
        # self.send_value("rmd","apos", 0, instance=self.prefix)

    def resetMultiturnValue(self):
        self.send_value("rmd","function", 1, instance=self.prefix)

    def setRmdCanId(self):
        pass

    def setRmdBaudrate(self):
        if self.rmdCanCheckBox.isChecked():
            self.send_value("rmd","baudrate", self.rmdBaudrateComboBox.currentIndex(), instance=self.prefix)

    def applyCanSettings(self):
        # spdPreset = str(self.comboBox_baud.currentIndex()+3) # 3 is lowest preset!
        # self.send_value("rmd","canspd",spdPreset,instance=self.prefix)
        canId = str(self.spinBox_id.value())
        self.send_value("rmd","canid", canId, instance=self.prefix)
        self.init_ui()  # Update UI

    def applyMaxTorque(self):
        torqueScaler = str(int(self.maxTorqueSpinBox.value() * 100))
        self.send_value("rmd","maxtorque", torqueScaler, instance=self.prefix)
