from PyQt4 import QtGui, QtCore
from scale_qt4 import MainWindow
import sys
import signal
import requests


def close(*args):
	QtGui.QApplication.quit()

signal.signal(signal.SIGINT, close)

class Window(MainWindow):
	def __init__(self):
		MainWindow.__init__(self)

	def getEnvData(self, p="Zračni tlak:  ", h="Vlažnost zraka: ", t="LJUBLJANA: "):
		data = requests.get("http://meteo.arso.gov.si/uploads/probase/www/observ/surface/text/sl/observationAms_LJUBL-ANA_BEZIGRAD_latest.rss")
		env_data = {}
		i = data.text.find(p)
		env_data["pressure"] = data.text[i+len(p):i+len(p)+4] + " mbar"

		i = data.text.find(h)
		env_data["humidity"] = data.text[i+len(h):i+len(h)+2] + " %"

		i = data.text.find(t)
		env_data["temperature"] = data.text[i+len(t):i+len(t)+2] + " °C"

		return env_data

	def updateEnvData(self):
		env_data = self.getEnvData()
		self.temp.setText(env_data["temperature"])
		self.humidity.setText(env_data["humidity"])
		self.tlak.setText(env_data["pressure"])

	def updateDisplay(self, mass):
		self.mass.setText(mass)

	def setStatus(self,status):
		self.status.setText(status)

	def findSerial(self):
		pass

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
	window = Window()
	window.show()

	# app.exec_()
	# t = Thread(name="rospy.spin",target=rospy.spin)
	# t.daemon = True
	# t.start()
	sys.exit(app.exec_())


runGui()