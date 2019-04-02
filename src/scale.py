from PyQt4 import QtGui, QtCore
from libra import Libra
from scale_qt4 import MainWindow
import sys
import signal
import serial

def close(*args):
	QtGui.QApplication.quit()

signal.signal(signal.SIGINT, close)

class Window(MainWindow):
	def __init__(self, libra):
		self.libra = libra
		MainWindow.__init__(self)
		self.timer_display = QtCore.QTimer()
		QtCore.QObject.connect(self.timer_display, QtCore.SIGNAL('timeout()'), self.updateDisplay)

		self.timer_display.start(1)  # 2 seconds

	def updateEnvData(self):
		env_data = self.libra.getEnvData()
		self.temp.setText(env_data["temperature"])
		self.humidity.setText(env_data["humidity"])
		self.tlak.setText(env_data["pressure"])

	def updateDisplay(self):
		data = self.libra.queue_backup.get()
		self.mass.display(data[2])
		self.status.setText(data[1])

	def setStatus(self,status):
		self.status.setText(status)

	def findSerial(self):
		print(list(serial.tools.list_ports.comports()))


	def connectSerial(self):
		pass

	def sendCommand(self):
		pass

	def setToZero(self):
		pass

	def setTo(self):
		pass

	def doCalibration(self):
		pass

	def saveToFile(self):
		w = QtGui.QWidget()
		w.resize(320, 240)
		w.setWindowTitle("Hello World!")

		self.filename = QtGui.QFileDialog.getSaveFileName(w, 'Save File', 'podatki.csv')

	def countPieces(self):
		pass

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
	# t = Thread(name="rospy.spin",target=rospy.spin)
	# t.daemon = True
	# t.start()
	sys.exit(app.exec_())


runGui()
