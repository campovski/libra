from PyQt4 import QtGui, QtCore
from libra import Libra
import libra
from scale_qt4 import MainWindow
import sys
import signal
import serial
import serial.tools.list_ports
import time
from threading import Thread

def close(*args):
	QtGui.QApplication.quit()

signal.signal(signal.SIGINT, close)

class Window(MainWindow):
	def __init__(self, libra):
		self.libra = libra
		MainWindow.__init__(self)
		t = Thread(name="updateDisplay", target=self.updateDisplay)
		t.daemon = True
		t.start()
		self.ports = []
		self.findSerial()
		# self.timer_display = QtCore.QTimer()
		# QtCore.QObject.connect(self.timer_display, QtCore.SIGNAL('timeout()'), self.updateDisplay)

		# self.timer_display.start(1)  # 2 seconds

	def updateEnvData(self):
		env_data = self.libra.getEnvData()
		self.temp.setText(env_data["temperature"])
		self.humidity.setText(env_data["humidity"])
		self.tlak.setText(env_data["pressure"])

	def updateDisplay(self):
		while 1:
			if not self.libra.queue_backup.empty():
				data = self.libra.queue_backup.get()
				if len(data) > 2:
					self.mass.display(data[2])
					self.status.setText(data[1])

			self.status_2.setText(str(self.libra.stabilization_time))
			self.count.setText(str(round(self.libra.count_results_once)))
			self.count_2.setText(str(self.libra.count_results_row))
			time.sleep(0.05)

	def setStatus(self,status):
		self.status.setText(status)

	def findSerial(self):
		# self.serial_port.addItems(list(serial.tools.list_ports.comports()))
		for p in serial.tools.list_ports.comports():
			if p.device not in self.ports:
				self.serial_port.addItem(p.device)
				self.ports.append(p.device)

	def connectSerial(self):
		pass

	def sendCommand(self):
		cmd = str(self.command.text())

		# cmd = "{0}\r\n".format(str(self.command.text())).encode('ascii')
		# self.libra.ser.write(cmd)
		data = self.libra.queue_backup.get()
		self.return_data.setText(data[0])

	def setToZero(self):
		# self.tara.setText(self.libra.setZero())
		self.libra.setZero()

	def setTo(self):
		self.libra.setTare(float(str(self.tara.text())))
		self.tara.setText(str(self.libra.current_tare))


	def doCalibration(self):
		weight = str(self.command.text())
		if not weight:
			weight = 100
		self.libra.calibrate(float(weight))

	def saveToFile(self):
		w = QtGui.QWidget()
		w.resize(320, 240)
		w.setWindowTitle("Hello World!")

		self.filename = QtGui.QFileDialog.getSaveFileName(w, 'Save File', 'podatki.csv')

	def calculatePieces(self):
		try:
			weight = float(self.weight.text())
		except:
			weight = None
			self.weight.setText("")

		self.libra.countApi(libra.COUNT_ONCE,target=weight)
		# self.count.setText(str(self.libra.countApi(libra.COUNT_ONCE)))

	def countPieces(self, stop):
		self.libra.countApi(libra.COUNT_ROW,not stop)
		# self.count_2.setText(str(self.libra.countApi(libra.COUNT_ROW)))

def runGui():
	app = QtGui.QApplication(sys.argv)
	window = Window(Libra(
        port="/dev/ttyUSB0",
        baudrate=2400,
        bytesize=serial.SEVENBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=True
    ))
	window.show()

	# app.exec_()

	sys.exit(app.exec_())


runGui()
